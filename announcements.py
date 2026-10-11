# -*- coding: utf-8 -*-
"""东财公告：按个股拉取并缓存到本地库，供 K 线旗杆日图标悬停展示当天重要消息。

tushare 的 anns_d / news 等公告接口当前 token 无权限，故走东财免 token 接口：
    https://np-anotice-stock.eastmoney.com/api/security/ann?stock_list=000001
列表缓存进 st_announcement 表，同一股票只拉一次，后续查询零请求。
"""
import logging
import re

import pymysql
import requests

logger = logging.getLogger('announcements')

_LIST_API = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
_DETAIL_BASE = 'https://data.eastmoney.com/notices/detail'
_HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
_PAGE_SIZE = 50
_MAX_PAGES = 8          # 8页=400条，覆盖单只股票一年以上的公告量
_REQUEST_TIMEOUT = 15


def _connect():
    return pymysql.connect(
        host='localhost', user='root', password='P@ssw0rd', database='stockshare',
        connect_timeout=15, read_timeout=15, write_timeout=15,
    )


def createAnnouncementTable():
    """建公告缓存表 st_announcement（幂等）"""
    db = _connect()
    try:
        cursor = db.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS st_announcement ("
            "  id INT AUTO_INCREMENT PRIMARY KEY,"
            "  st_code VARCHAR(12) NOT NULL COMMENT '股票代码 000001.SZ',"
            "  ann_date VARCHAR(8) NOT NULL COMMENT '公告日期 YYYYMMDD',"
            "  title VARCHAR(255) NOT NULL COMMENT '公告标题',"
            "  art_code VARCHAR(32) NOT NULL COMMENT '东财公告编号',"
            "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "  UNIQUE KEY uk_code_art (st_code, art_code),"
            "  KEY idx_code_date (st_code, ann_date)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
        db.commit()
    finally:
        db.close()


def _symbol(st_code):
    """000001.SZ -> 000001"""
    return st_code.split('.')[0]


def _to_yyyymmdd(value):
    """'2026-09-30 00:00:00' / '2026-09-30' -> '20260930'"""
    digits = re.sub(r'\D', '', value or '')
    return digits[:8] if len(digits) >= 8 else ''


def _detail_url(st_code, art_code):
    return f'{_DETAIL_BASE}/{_symbol(st_code)}/{art_code}.html'


def fetchAnnouncements(st_code, stop_before='', max_pages=_MAX_PAGES):
    """分页拉取该股公告并 upsert 入库，返回入库条数。

    stop_before：拉到早于该日期（YYYYMMDD）的公告即停止，避免无谓请求。
    """
    st_code = st_code.upper()
    symbol = _symbol(st_code)
    saved = 0
    page = 1
    earliest = ''
    while page <= max_pages:
        try:
            resp = requests.get(
                _LIST_API,
                params={
                    'sr': -1, 'page_size': _PAGE_SIZE, 'page_index': page,
                    'ann_type': 'A', 'client_source': 'web',
                    'stock_list': symbol, 'f_node': 0, 's_node': 0,
                },
                headers=_HEADERS, timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            logger.warning('拉取公告失败 %s 第%s页: %s', st_code, page, exc)
            break
        items = (payload.get('data') or {}).get('list') or []
        if not items:
            break
        rows = []
        for item in items:
            ann_date = _to_yyyymmdd(item.get('notice_date'))
            title = (item.get('title') or '').strip()
            art_code = item.get('art_code') or ''
            if not (ann_date and title and art_code):
                continue
            rows.append((st_code, ann_date, title[:255], art_code))
            if not earliest or ann_date < earliest:
                earliest = ann_date
        if rows:
            saved += _upsert(rows)
        if earliest and stop_before and earliest < stop_before:
            break
        page += 1
    logger.info('公告拉取完成 %s：%s 条（最早 %s）', st_code, saved, earliest)
    return saved


def _upsert(rows):
    db = _connect()
    try:
        cursor = db.cursor()
        cursor.executemany(
            "INSERT INTO st_announcement (st_code, ann_date, title, art_code) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE title=VALUES(title), ann_date=VALUES(ann_date)",
            rows,
        )
        db.commit()
        return cursor.rowcount
    finally:
        db.close()


def _cached_range(st_code):
    """返回本地已缓存的该股公告日期范围，无缓存时 (None, None)"""
    db = _connect()
    try:
        cursor = db.cursor()
        cursor.execute(
            "SELECT MIN(ann_date), MAX(ann_date) FROM st_announcement WHERE st_code=%s",
            (st_code,))
        return cursor.fetchone()
    finally:
        db.close()


def getMessages(st_code, ann_date, refresh=False):
    """取该股某日（YYYYMMDD）公告列表；缓存缺失时先补拉，返回 dict 列表。"""
    st_code = st_code.upper()
    if refresh:
        fetchAnnouncements(st_code, stop_before=ann_date)
    else:
        earliest, _ = _cached_range(st_code)
        # 无缓存，或缓存还没覆盖到目标日期之前 -> 补拉一次
        if earliest is None or ann_date < earliest:
            fetchAnnouncements(st_code, stop_before=ann_date)
    db = _connect()
    try:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT ann_date, title, art_code FROM st_announcement "
            "WHERE st_code=%s AND ann_date=%s ORDER BY art_code DESC",
            (st_code, ann_date))
        rows = cursor.fetchall()
    finally:
        db.close()
    return [
        {
            'date': r['ann_date'],
            # 标题形如“平安银行:董事会决议公告”，去掉冗余的公司名前缀
            'title': re.sub(r'^[^:：]{1,20}[:：]', '', r['title']),
            'url': _detail_url(st_code, r['art_code']),
        }
        for r in rows
    ]


def getMessagesInRange(st_code, start_date, end_date, refresh=False):
    """取该股 [start_date, end_date]（YYYYMMDD，含端点）区间内的公告列表。

    缓存缺失时先补拉历史（保证覆盖到 start_date 之前）。
    """
    st_code = st_code.upper()
    if refresh:
        fetchAnnouncements(st_code, stop_before=start_date)
    else:
        earliest, _ = _cached_range(st_code)
        if earliest is None or start_date < earliest:
            fetchAnnouncements(st_code, stop_before=start_date)
    db = _connect()
    try:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT ann_date, title, art_code FROM st_announcement "
            "WHERE st_code=%s AND ann_date>=%s AND ann_date<=%s "
            "ORDER BY ann_date DESC, art_code DESC",
            (st_code, start_date, end_date))
        rows = cursor.fetchall()
    finally:
        db.close()
    return [
        {
            'date': r['ann_date'],
            'title': re.sub(r'^[^:：]{1,20}[:：]', '', r['title']),
            'url': _detail_url(st_code, r['art_code']),
        }
        for r in rows
    ]
