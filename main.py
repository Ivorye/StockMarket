import time
import os
import csv
import re
import datetime
import pymysql
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

app = FastAPI(title="StockMarket 筛选系统")
# 注意：Jinja2 3.1.6 的模板 LRU 缓存在 Python 3.14 下会抛
# TypeError: cannot use 'tuple' as a dict key，故禁用模板缓存以规避。
_loader = FileSystemLoader("templates")
_env = Environment(loader=_loader, cache_size=0, autoescape=True)
templates = Jinja2Templates(env=_env)


@app.on_event("startup")
def _init_db():
    import stockPolicy as sp
    sp.createSignalTable()
    sp.ensureStocksNameColumn()


# 内存缓存: {cache_key: (timestamp, data)}
_cache = {}
_CACHE_TTL = 1800  # 30分钟
_DB_TIMEOUT_SECONDS = 15


def _connect_db(timeout_seconds=_DB_TIMEOUT_SECONDS):
    return pymysql.connect(
        host='localhost', user='root', password='P@ssw0rd', database='stockshare',
        connect_timeout=timeout_seconds,
        read_timeout=timeout_seconds,
        write_timeout=timeout_seconds,
    )


def _eastmoney_url(st_code: str) -> str:
    """根据股票代码生成东方财富链接，如 000001.SZ -> https://quote.eastmoney.com/sz000001.html"""
    parts = st_code.split('.')
    if len(parts) == 2:
        symbol, exchange = parts[0], parts[1].lower()
        return f'https://quote.eastmoney.com/{exchange}{symbol}.html'
    return '#'


templates.env.globals['eastmoney_url'] = _eastmoney_url


def _load_backtest_results():
    """載入完整回測彙總；檔案不存在時回傳可渲染的空狀態。"""
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'output', 'backtest_smooth_uptrend_full')
    summary_path = os.path.join(base_dir, 'summary.csv')
    yearly_path = os.path.join(base_dir, 'yearly_summary.csv')
    result = {'available': False, 'summary': [], 'yearly': [],
              'signal_count': 0, 'conclusion': ''}
    try:
        db = _connect_db()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT run_id FROM st_backtest_run WHERE strategy='smooth_uptrend' AND status='completed' ORDER BY completed_at DESC LIMIT 1")
        latest = cursor.fetchone()
        if latest:
            cursor.execute("SELECT * FROM st_backtest_summary WHERE run_id=%s AND period_type='all' ORDER BY horizon", (latest['run_id'],))
            result['summary'] = cursor.fetchall()
            cursor.execute("SELECT * FROM st_backtest_summary WHERE run_id=%s AND period_type='year' ORDER BY period_value,horizon", (latest['run_id'],))
            result['yearly'] = cursor.fetchall()
            result['available'] = bool(result['summary'])
            result['signal_count'] = result['summary'][0]['signals'] if result['summary'] else 0
            result['conclusion'] = ('各持有期勝率均低於50%，且中位報酬為負；平均報酬受到少數大漲樣本拉高，'
                                    '目前不適合單獨作為買入訊號。')
            db.close()
            return result
        db.close()
    except Exception:
        pass
    if not os.path.exists(summary_path):
        return result
    numeric_fields = {'horizon', 'signals', 'win_rate_pct', 'avg_return_pct',
                      'median_return_pct', 'avg_mfe_pct', 'median_mfe_pct',
                      'avg_mae_pct', 'median_mae_pct'}
    with open(summary_path, newline='', encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            for key in numeric_fields:
                if key in row:
                    row[key] = int(float(row[key])) if key in ('horizon', 'signals') else float(row[key])
            result['summary'].append(row)
    if os.path.exists(yearly_path):
        with open(yearly_path, newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                for key in numeric_fields:
                    if key in row:
                        row[key] = int(float(row[key])) if key in ('horizon', 'signals') else float(row[key])
                result['yearly'].append(row)
    result['available'] = bool(result['summary'])
    result['signal_count'] = result['summary'][0]['signals'] if result['summary'] else 0
    result['conclusion'] = ('各持有期勝率均低於50%，且中位報酬為負；平均報酬受到少數大漲樣本拉高，'
                            '目前不適合單獨作為買入訊號。')
    return result


def _load_yearly_double_results():
    """最近一年内，从最低点 low 到之后最高点 high 至少翻倍的股票。"""
    cache_key = '__yearly_double__'
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data

    result = {
        'available': False,
        'start_date': '',
        'end_date': '',
        'scanned': 0,
        'count': 0,
        'items': [],
    }
    db = _connect_db(timeout_seconds=120)
    try:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (600 * 1000,))
        cursor.execute("SELECT MAX(trade_date) AS max_date FROM st_daily")
        row = cursor.fetchone()
        end_date = row['max_date'] if row else ''
        if not end_date:
            return result
        start_date = (datetime.datetime.strptime(end_date, '%Y%m%d').date()
                      - datetime.timedelta(days=365)).strftime('%Y%m%d')

        # 两阶段查询，避免一次性拉取 100 万+ 行并做 filesort：
        # 阶段1：按代码聚合 MIN(low)/MAX(high)，只靠一个全表聚合筛出候选（翻倍下界）。
        cursor.execute(
            "SELECT ts_code, MIN(low) AS min_low, MAX(high) AS max_high "
            "FROM st_daily WHERE trade_date BETWEEN %s AND %s "
            "AND low>0 AND high>0 GROUP BY ts_code",
            (start_date, end_date),
        )
        scanned = 0
        candidates = []
        for r in cursor.fetchall():
            scanned += 1
            min_low = r['min_low']
            max_high = r['max_high']
            if min_low and max_high and max_high / min_low >= 2:
                candidates.append(r['ts_code'])

        # 阶段2：仅对候选代码做有序扫描（走 PRIMARY(ts_code,trade_date) 前缀），
        # 逐只在 Python 中复现"低点后高点翻倍"判定，返回行数从百万级降到数千级。
        items = []
        names = _load_stock_names(cursor, candidates)
        batch_size = 500
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            placeholders = ','.join(['%s'] * len(batch))
            cursor.execute(
                "SELECT ts_code, trade_date, low, high, closep FROM st_daily "
                "WHERE ts_code IN (" + placeholders + ") AND trade_date BETWEEN %s AND %s "
                "AND low>0 AND high>0 ORDER BY ts_code, trade_date",
                tuple(batch) + (start_date, end_date),
            )
            cur_code = None
            min_low = None
            min_date = ''
            best_high = None
            best_date = ''
            latest_close = None
            for r in cursor.fetchall():
                code = r['ts_code']
                if code != cur_code:
                    if cur_code is not None and min_low and best_high / min_low >= 2:
                        items.append(_double_item(cur_code, names.get(cur_code, ''),
                                                  min_date, min_low, best_date, best_high, latest_close))
                    cur_code = code
                    min_low = None
                    min_date = ''
                    best_high = None
                    best_date = ''
                    latest_close = None
                low = float(r['low'])
                high = float(r['high'])
                if min_low is None or low < min_low:
                    min_low = low
                    min_date = r['trade_date']
                    best_high = high
                    best_date = r['trade_date']
                if high > best_high:
                    best_high = high
                    best_date = r['trade_date']
                if r['closep'] is not None:
                    latest_close = float(r['closep'])
            if cur_code is not None and min_low and best_high / min_low >= 2:
                items.append(_double_item(cur_code, names.get(cur_code, ''),
                                          min_date, min_low, best_date, best_high, latest_close))

        items.sort(key=lambda item: item['gain_pct'], reverse=True)
        result.update({
            'available': True,
            'start_date': start_date,
            'end_date': end_date,
            'scanned': scanned,
            'count': len(items),
            'items': items[:200],
        })
        _cache[cache_key] = (now, result)
        return result
    finally:
        db.close()


def _load_stock_names(cursor, candidates):
    """批量读取候选代码的股票名称，避免在主查询里 JOIN 放大行数。"""
    names = {}
    batch_size = 1000
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        placeholders = ','.join(['%s'] * len(batch))
        cursor.execute(
            "SELECT st_code, COALESCE(NULLIF(name,''), fullname, '') AS name "
            "FROM stocks WHERE st_code IN (" + placeholders + ")",
            tuple(batch),
        )
        for r in cursor.fetchall():
            if isinstance(r, dict):
                names[r['st_code']] = r['name']
            else:
                names[r[0]] = r[1]
    return names


def _double_item(st_code, name, min_date, min_low, best_date, best_high, latest_close):
    """构造单只翻倍股的结果记录。"""
    gain_since = round((latest_close / min_low - 1) * 100, 1) if latest_close and latest_close > 0 and min_low > 0 else None
    return {
        'st_code': st_code,
        'name': name,
        'eastmoney_url': _eastmoney_url(st_code),
        'low_date': min_date,
        'low_price': round(min_low, 2),
        'high_date': best_date,
        'high_price': round(best_high, 2),
        'gain_pct': round((best_high / min_low - 1) * 100, 1),
        'latest_close': round(latest_close, 2) if latest_close is not None else None,
        'gain_since_pct': gain_since,
        'high_drawdown_pct': round((latest_close - best_high) / best_high * 100, 1) if latest_close is not None and best_high and best_high > 0 else None,
    }


def _save_signals(rows, strategy, trade_date):
    """将策略筛选结果写入 st_daily_signal 表和 CSV 文件"""
    if not rows:
        return
    try:
        db = _connect_db()
        cursor = db.cursor()
        sql = "INSERT IGNORE INTO st_daily_signal(trade_date,st_code,strategy,closePrice,pct_chg,vol,prev_vol,vol_ratio) " \
              "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)"
        csv_rows = []
        for r in rows:
            cursor.execute(sql, (trade_date, r['st_code'], strategy, r['closep'], r['pct_chg'], r['vol'], r['prev_vol'], r['vol_ratio']))
            csv_rows.append([trade_date, r['st_code'], strategy, r['closep'], r['pct_chg'], r['vol'], r['prev_vol'], r['vol_ratio']])
        db.commit()
        cursor.close()
        db.close()
        if csv_rows:
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, f'signals_{trade_date}.csv')
            write_header = not os.path.exists(filepath)
            with open(filepath, 'a', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                if write_header:
                    w.writerow(['trade_date', 'st_code', 'strategy', 'closePrice', 'pct_chg', 'vol', 'prev_vol', 'vol_ratio'])
                w.writerows(csv_rows)
    except Exception as e:
        print(f'_save_signals [{strategy}] error: {e}')


def _run_combined_strategy(date_str=''):
    """执行三个策略并返回对比结果，带内存缓存"""
    cache_key = date_str or '__latest__'
    now = time.time()

    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data

    db = _connect_db()
    cursor = db.cursor()
    cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (_DB_TIMEOUT_SECONDS * 1000,))

    # 获取最新交易日和前一个交易日
    cursor.execute("SELECT MAX(trade_date) FROM st_daily")
    latest_date = cursor.fetchone()[0]

    if date_str:
        target = date_str
        cursor.execute("SELECT DISTINCT trade_date FROM st_daily WHERE trade_date <= %s ORDER BY trade_date DESC LIMIT 2", (target,))
    else:
        cursor.execute("SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT 2")

    dates = cursor.fetchall()
    if len(dates) < 2:
        db.close()
        return {'today': latest_date, 'prev_day': '', 's1': [], 's2': [], 'combined': [],
                'smooth': [], 'smooth_start': '', 'latest_date': latest_date}

    today = dates[0][0]
    prev_day = dates[1][0]

    s1, s2, combined = [], [], []

    cursor.execute(
        "SELECT t.symbol, t.ts_code, t.openp, t.high, t.low, t.closep, "
        "t.pct_chg, t.vol, p.high, p.closep, p.vol "
        "FROM st_daily t JOIN st_daily p ON p.ts_code=t.ts_code "
        "WHERE t.trade_date=%s AND p.trade_date=%s "
        "AND t.symbol NOT LIKE '688%%'",
        (today, prev_day))

    raw_rows = cursor.fetchall()
    name_map = _load_stock_names(cursor, [r[1] for r in raw_rows])

    for row_data in raw_rows:
        (symbol, st_code, today_open, today_high, today_low,
         today_close, today_pct_chg, today_vol,
         prev_high, prev_close, prev_vol) = row_data

        vol_ratio = round(today_vol / prev_vol, 2) if prev_vol > 0 else 0
        gap_size = round(today_low - prev_high, 2) if today_low > prev_high else 0

        has_gap = today_low > prev_high
        is_surge = prev_vol > 0 and today_vol >= prev_vol * 3
        big_gain = today_pct_chg > 6

        row = {
            'symbol': symbol, 'st_code': st_code,
            'name': name_map.get(st_code, ''),
            'openp': today_open, 'high': today_high,
            'low': today_low, 'closep': today_close,
            'pct_chg': round(today_pct_chg, 2),
            'vol': today_vol, 'prev_vol': prev_vol,
            'vol_ratio': vol_ratio, 'gap_size': gap_size,
            'prev_high': prev_high, 'prev_close': prev_close,
            'has_gap': has_gap, 'is_surge': is_surge, 'big_gain': big_gain,
        }

        if is_surge and big_gain:
            s1.append(row)
        if has_gap:
            s2.append(row)
        if has_gap and is_surge and big_gain:
            combined.append(row)

    s1.sort(key=lambda x: x['pct_chg'], reverse=True)
    s2.sort(key=lambda x: x['pct_chg'], reverse=True)
    combined.sort(key=lambda x: x['pct_chg'], reverse=True)

    import stockPolicy as sp
    if date_str:
        cursor.execute("SELECT DISTINCT trade_date FROM st_daily WHERE trade_date<=%s ORDER BY trade_date DESC LIMIT 30", (today,))
    else:
        cursor.execute("SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT 30")
    smooth_dates = [row[0] for row in cursor.fetchall()][::-1]
    smooth = []
    if len(smooth_dates) == 30:
        placeholders = ','.join(['%s'] * 30)
        cursor.execute(
            "SELECT d.ts_code,COALESCE(NULLIF(s.name,''),s.fullname,''),d.closep FROM st_daily d "
            "LEFT JOIN stocks s ON s.st_code=d.ts_code "
            f"WHERE d.trade_date IN ({placeholders}) AND d.symbol NOT LIKE '688%%' "
            "ORDER BY d.ts_code,d.trade_date", tuple(smooth_dates))
        grouped = {}
        for st_code, sname, closep in cursor.fetchall():
            item = grouped.setdefault(st_code, {'name': sname, 'closes': []})
            item['closes'].append(float(closep))
        for st_code, item in grouped.items():
            if len(item['closes']) != 30:
                continue
            metrics = sp._smooth_uptrend_metrics(item['closes'])
            if (metrics and metrics['gain_pct'] > 30 and metrics['slope'] > 0
                    and metrics['r_squared'] >= 0.8 and metrics['up_ratio'] >= 0.6
                    and metrics['max_drawdown_pct'] <= 10):
                smooth.append({
                    'st_code': st_code, 'name': item['name'],
                    'gain_pct': round(metrics['gain_pct'], 2),
                    'max_drawdown_pct': round(metrics['max_drawdown_pct'], 2),
                    'r_squared': round(metrics['r_squared'], 3),
                    'up_ratio': round(metrics['up_ratio'] * 100, 1),
                    'start_close': round(item['closes'][0], 2),
                    'end_close': round(item['closes'][-1], 2),
                })
        smooth.sort(key=lambda x: x['gain_pct'], reverse=True)
    db.close()

    # 将策略结果写入 st_daily_signal 表
    _save_signals(s1, '放量涨幅', today)
    _save_signals(s2, '跳空缺口', today)
    _save_signals(combined, '跳空放量涨幅', today)

    data = {
        'today': today, 'prev_day': prev_day,
        's1': s1, 's2': s2, 'combined': combined,
        'smooth': smooth,
        'smooth_start': smooth_dates[0] if smooth_dates else '',
        'latest_date': latest_date,
    }

    _cache[cache_key] = (now, data)
    return data


def _anchor_dates(anchor='', limit=10):
    """返回 <= anchor 的最近 limit 个交易日（升序）。anchor 为空则取最新。"""
    db = _connect_db()
    try:
        cursor = db.cursor()
        if anchor:
            cursor.execute("SELECT DISTINCT trade_date FROM st_daily WHERE trade_date<=%s "
                           "ORDER BY trade_date DESC LIMIT %s", (anchor, limit))
        else:
            cursor.execute("SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT %s",
                           (limit,))
        rows = [r[0] for r in cursor.fetchall()]
        cursor.close()
    finally:
        db.close()
    return rows[::-1]


def _load_bull_flag(anchor='', trading_days=10):
    """以 anchor 为基准日，向前 trading_days 个交易日内成型的上升旗形，带内存缓存。"""
    cache_key = f'__bull_flag__|{anchor}|{trading_days}'
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data

    start_date, signal_date, items = '', '', []
    try:
        dates = _anchor_dates(anchor, trading_days)
        if dates:
            signal_date, start_date = dates[-1], dates[0]
    except Exception as e:
        print(f'_load_bull_flag dates error: {e}')

    try:
        import stockPolicy as sp
        # endDate 决定扫描窗口：小旗杆/旗形的信号日以 anchor 为基准，而非库中最新日期
        items = sp.scanBullFlag(trading_days=trading_days, endDate=anchor)
    except Exception as e:
        print(f'_load_bull_flag error: {e}')

    data = {
        'records': items,
        'count': len(items),
        'start_date': start_date,
        'signal_date': signal_date,
        'trading_days': trading_days,
    }
    _cache[cache_key] = (now, data)
    return data


def _load_small_pole(anchor='', **params):
    """以 anchor 为基准日的小旗杆形态，带内存缓存。"""
    need = params.get('lookback', 10) + params.get('prev_vol_days', 5)
    cache_key = f'__small_pole__|{anchor}|{need}'
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data

    start_date, signal_date, records = '', '', []
    try:
        dates = _anchor_dates(anchor, need)
        if dates:
            signal_date, start_date = dates[-1], dates[0]
    except Exception as e:
        print(f'_load_small_pole dates error: {e}')

    try:
        import stockPolicy as sp
        records = sp.scanSmallPole(endDate=anchor, **params)
    except Exception as e:
        print(f'_load_small_pole error: {e}')

    data = {
        'records': records,
        'count': len(records),
        'start_date': start_date,
        'signal_date': signal_date,
    }
    _cache[cache_key] = (now, data)
    return data


@app.get("/", response_class=HTMLResponse, tags=["page"])
@app.get("/combined", response_class=HTMLResponse, tags=["page"])
async def combined_page(request: Request, date: str = ''):
    """跳空放量涨幅合并策略页面"""
    data = _run_combined_strategy(date)
    return templates.TemplateResponse(request, "combined.html", {
        "data": data,
        "backtest": _load_backtest_results(),
        "yearly_double": {'count': '-', 'items': [], 'start_date': '', 'scanned': 0},
        # 以用户输入的查询日期为基准；未输入时退回到页面当日（库中最新交易日）
        "bull_flag": _load_bull_flag(anchor=date or data['today'], trading_days=10),
        "small_pole": _load_small_pole(anchor=date or data['today']),
        "date": date or data['today'],
    })



@app.get("/api/yearly-double", tags=["data"])
async def yearly_double_data():
    """返回最近一年低点后高点翻倍股票。"""
    return _load_yearly_double_results()


@app.get("/api/search-stock", tags=["data"])
async def search_stock(q: str = '', limit: int = 10):
    """按股票代码或名称模糊搜索，返回候选列表。"""
    keyword = (q or '').strip()
    if not keyword:
        return []
    limit = max(1, min(limit, 20))
    db = _connect_db()
    try:
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT st_code AS code, COALESCE(NULLIF(name,''), fullname) AS name "
            "FROM stocks "
            "WHERE st_code LIKE %s OR name LIKE %s OR fullname LIKE %s "
            "ORDER BY st_code "
            "LIMIT %s",
            (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', limit),
        )
        rows = cursor.fetchall()
    finally:
        db.close()
    return [
        {
            'code': row['code'],
            'name': row['name'],
            'eastmoney_url': _eastmoney_url(row['code']),
        }
        for row in rows
    ]


@app.get("/api/kline/{st_code}", tags=["data"])
async def kline_data(st_code: str, days: int = 60, end_date: str = ''):
    """返回指定股票的 K 線與成交量資料。"""
    st_code = st_code.upper()
    if not re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", st_code):
        return JSONResponse({"error": "股票代碼格式不正確"}, status_code=400)
    days = max(20, min(days, 240))
    db = _connect_db()
    try:
        cursor = db.cursor()
        cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (_DB_TIMEOUT_SECONDS * 1000,))
        date_filter = "AND d.trade_date<=%s" if end_date else ""
        params = (st_code, end_date, days) if end_date else (st_code, days)
        cursor.execute(
            "SELECT d.trade_date,d.openp,d.high,d.low,d.closep,d.vol,"
            "COALESCE(NULLIF(s.name,''),s.fullname,'') FROM st_daily d "
            "LEFT JOIN stocks s ON s.st_code=d.ts_code "
            f"WHERE d.ts_code=%s {date_filter} "
            "ORDER BY d.trade_date DESC LIMIT %s", params)
        rows = cursor.fetchall()[::-1]
    finally:
        db.close()
    return {
        "st_code": st_code,
        "name": rows[0][6] if rows else "",
        "items": [
            {"date": r[0], "open": r[1], "high": r[2], "low": r[3],
             "close": r[4], "volume": r[5]}
            for r in rows
        ],
    }


@app.get("/api/kline/{st_code}/shift", tags=["data"])
async def shift_kline_data(st_code: str, end_date: str, direction: int, days: int = 120):
    """依實際交易日向前或向後移動 K 線截止日。"""
    st_code = st_code.upper()
    if not re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", st_code) or direction not in (-1, 1):
        return JSONResponse({"error": "參數不正確"}, status_code=400)
    operator = "<" if direction < 0 else ">"
    order = "DESC" if direction < 0 else "ASC"
    db = _connect_db()
    try:
        cursor = db.cursor()
        cursor.execute(
            f"SELECT trade_date FROM st_daily WHERE ts_code=%s AND trade_date{operator}%s "
            f"ORDER BY trade_date {order} LIMIT 1", (st_code, end_date))
        row = cursor.fetchone()
    finally:
        db.close()
    if not row:
        return JSONResponse({"error": "已到可用交易日邊界"}, status_code=404)
    return await kline_data(st_code, days, row[0])
