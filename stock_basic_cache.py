"""股票列表的每日刷新、跨进程互斥和失败冷却；不主动执行任何 API 请求。"""
import datetime
import logging
from contextlib import contextmanager

import pandas as pd

import db_utils


logger = logging.getLogger(__name__)
LOCK_NAME = 'stockshare.stock_basic.refresh'
COOLDOWN = datetime.timedelta(hours=1, seconds=5)
REQUIRED_COLUMNS = ('ts_code', 'symbol', 'name', 'fullname', 'list_date')


@contextmanager
def _refresh_lock():
    connection = db_utils.connect_pymysql()
    acquired = False
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT GET_LOCK(%s, 0)', (LOCK_NAME,))
            acquired = cursor.fetchone()[0] == 1
        yield connection if acquired else None
    finally:
        try:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT RELEASE_LOCK(%s)', (LOCK_NAME,))
        finally:
            connection.close()


def read_cached_stocks(connection=None):
    own_connection = connection is None
    connection = connection if connection is not None else db_utils.connect_pymysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT st_code AS ts_code,symbol,name,fullname,list_date FROM stocks')
            rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=REQUIRED_COLUMNS) if rows else None
    finally:
        if own_connection:
            connection.close()


def _ensure_state_table(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            'CREATE TABLE IF NOT EXISTS st_api_request_state ('
            'api_name VARCHAR(64) NOT NULL PRIMARY KEY,'
            'next_allowed_at DATETIME NOT NULL,'
            'last_success_date VARCHAR(8) DEFAULT NULL'
            ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
        )
    connection.commit()


def _read_state(connection):
    with connection.cursor() as cursor:
        cursor.execute('SELECT next_allowed_at,last_success_date FROM st_api_request_state WHERE api_name=%s',
                       ('stock_basic',))
        return cursor.fetchone()


def _reserve_attempt(connection, next_allowed_at):
    # 在调用 API 之前提交，进程异常退出后也保留冷却时间。
    with connection.cursor() as cursor:
        cursor.execute(
            'INSERT INTO st_api_request_state(api_name,next_allowed_at) VALUES(%s,%s) '
            'ON DUPLICATE KEY UPDATE next_allowed_at=%s',
            ('stock_basic', next_allowed_at, next_allowed_at)
        )
    connection.commit()


def _save_stocks(connection, frame):
    """一次事务更新整份列表，不用返回行号作为股票主键，也不静默忽略新股。"""
    if frame is None or frame.empty:
        raise ValueError('stock_basic 返回空列表，不标记刷新成功')
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing or frame[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError('stock_basic 返回数据缺少必需字段或含空值: %s' % sorted(missing))
    if frame.ts_code.duplicated().any():
        raise ValueError('stock_basic 返回重复股票代码')

    with connection.cursor() as cursor:
        cursor.execute('SELECT id,st_code FROM stocks')
        existing = cursor.fetchall()
        ids_by_code = {}
        for stock_id, code in existing:
            ids_by_code.setdefault(code, []).append(stock_id)
        next_id = max((row[0] for row in existing), default=0)
        for row in frame.itertuples(index=False):
            values = (str(row.symbol), str(row.name), str(row.fullname), str(row.list_date))
            if row.ts_code in ids_by_code:
                # stocks 目前没有 st_code 索引；用已匹配的主键更新，避免每条都扫描全表。
                for stock_id in ids_by_code[row.ts_code]:
                    cursor.execute('UPDATE stocks SET symbol=%s,name=%s,fullname=%s,list_date=%s WHERE id=%s',
                                   values + (stock_id,))
            else:
                next_id += 1
                cursor.execute('INSERT INTO stocks(id,symbol,name,fullname,list_date,st_code) VALUES(%s,%s,%s,%s,%s,%s)',
                               (next_id,) + values + (str(row.ts_code),))
                ids_by_code[row.ts_code] = [next_id]


def _record_success(connection, today, source):
    source = source if source in ('manual', 'system') else 'system'
    with connection.cursor() as cursor:
        cursor.execute('UPDATE st_api_request_state SET last_success_date=%s WHERE api_name=%s',
                       (today, 'stock_basic'))
        cursor.execute(
            'INSERT INTO st_execution_status(task_name,exec_date,source,status) VALUES(%s,%s,%s,%s) '
            'ON DUPLICATE KEY UPDATE exec_date=%s,source=%s,status=%s',
            ('stock_basic', today, source, 'Y', today, source, 'Y')
        )
    # 股票列表及两个成功状态同时提交，避免成功状态与缓存不一致。
    connection.commit()


def _cached_result(frame, reason, warning=False):
    if frame is None or frame.empty:
        raise RuntimeError('股票列表暂不可用，且 stocks 无缓存：' + reason)
    frame.attrs['stock_basic_source'] = 'stocks'
    frame.attrs['stock_basic_reason'] = reason
    log = logger.warning if warning else logger.info
    log('股票列表来源=stocks，数量=%s；%s', len(frame), reason)
    return frame


def _refresh(connection, fetch, source):
    cached = read_cached_stocks(connection)
    _ensure_state_table(connection)
    today = datetime.date.today().strftime('%Y%m%d')
    now = datetime.datetime.now()
    state = _read_state(connection)
    successful_today = (state is not None and state[1] == today)
    if not successful_today:
        # 兼容升级前已经写入的每日成功状态。
        successful_today = db_utils.check_execution_status('stock_basic', exec_date=today, driver='pymysql')
    if successful_today and cached is not None and not cached.empty:
        return _cached_result(cached, '今天已成功刷新，不再调用 stock_basic')
    if state is not None and state[0] > now:
        return _cached_result(cached, 'stock_basic 冷却至 %s，跳过 API；列表可能尚未更新' % state[0], warning=True)

    _reserve_attempt(connection, now + COOLDOWN)
    try:
        fresh = fetch()
        _save_stocks(connection, fresh)
        _record_success(connection, today, source)
    except Exception as exc:
        connection.rollback()
        message = str(exc)
        # 日额度耗尽时，等待到次日；小时限制及其他失败至少冷却一小时。
        if '次/天' in message or '次/日' in message:
            tomorrow = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time())
            _reserve_attempt(connection, max(tomorrow, datetime.datetime.now() + COOLDOWN))
        return _cached_result(cached, '刷新失败，使用已有缓存；%s' % exc, warning=True)
    fresh.attrs['stock_basic_source'] = 'api'
    fresh.attrs['stock_basic_reason'] = '当天首次成功刷新并已入库'
    logger.info('股票列表来源=API，数量=%s，已更新 stocks 及当天成功状态', len(fresh))
    return fresh


def get_stock_basic(fetch, source='system'):
    """所有参与此协议的进程共用数据库锁及持久化冷却，不重试 API。"""
    try:
        with _refresh_lock() as connection:
            if connection is None:
                return _cached_result(read_cached_stocks(), '另一进程正在刷新 stock_basic，跳过 API', warning=True)
            return _refresh(connection, fetch, source)
    except Exception as exc:
        # 状态/锁不可用时不冒险绕过限制请求 API；有缓存则继续运行。
        return _cached_result(read_cached_stocks(), '刷新控制不可用，未继续请求 API；%s' % exc, warning=True)
