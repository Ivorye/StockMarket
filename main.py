import time
import mysql.connector
import pymysql
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="StockMarket 筛选系统")
templates = Jinja2Templates(directory="templates")

# 内存缓存: {cache_key: (timestamp, data)}
_cache = {}
_CACHE_TTL = 1800  # 30分钟


def _eastmoney_url(st_code: str) -> str:
    """根据股票代码生成东方财富链接，如 000001.SZ -> https://quote.eastmoney.com/sz000001.html"""
    parts = st_code.split('.')
    if len(parts) == 2:
        symbol, exchange = parts[0], parts[1].lower()
        return f'https://quote.eastmoney.com/{exchange}{symbol}.html'
    return '#'


templates.env.globals['eastmoney_url'] = _eastmoney_url


def _connect_sm():
    return mysql.connector.connect(host="localhost", user="root", passwd="P@ssw0rd", database='stockshare')


def _run_combined_strategy(date_str=''):
    """执行三个策略并返回对比结果，带内存缓存"""
    cache_key = date_str or '__latest__'
    now = time.time()

    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data

    db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
    cursor = db.cursor()

    # 获取最新交易日和前一个交易日
    cursor.execute('SELECT MAX(trade_date) FROM `gp000001`')
    latest_date = cursor.fetchone()[0]

    if date_str:
        target = date_str
        cursor.execute('SELECT DISTINCT trade_date FROM `gp000001` WHERE trade_date <= %s ORDER BY trade_date DESC LIMIT 2', (target,))
    else:
        cursor.execute('SELECT DISTINCT trade_date FROM `gp000001` ORDER BY trade_date DESC LIMIT 2')

    dates = cursor.fetchall()
    if len(dates) < 2:
        db.close()
        return {'today': latest_date, 'prev_day': '', 's1': [], 's2': [], 'combined': [], 'latest_date': latest_date}

    today = dates[0][0]
    prev_day = dates[1][0]

    cursor.execute('SELECT symbol, st_code FROM stocks')
    stocks = cursor.fetchall()

    s1, s2, combined = [], [], []

    for symbol, st_code in stocks:
        if symbol.startswith('688'):
            continue
        table = '`gp%s`' % symbol
        try:
            cursor.execute(
                'SELECT trade_date, openp, high, low, closep, pct_chg, vol '
                'FROM %s WHERE trade_date IN (%%s, %%s) ORDER BY trade_date' % table,
                (prev_day, today))
            rows = cursor.fetchall()
            if len(rows) != 2:
                continue

            prev_data, today_data = rows
            prev_high = prev_data[2]
            prev_close = prev_data[4]
            prev_vol = prev_data[6]
            today_open = today_data[1]
            today_high = today_data[2]
            today_low = today_data[3]
            today_close = today_data[4]
            today_pct_chg = today_data[5]
            today_vol = today_data[6]

            vol_ratio = round(today_vol / prev_vol, 2) if prev_vol > 0 else 0
            gap_size = round(today_low - prev_high, 2) if today_low > prev_high else 0

            has_gap = today_low > prev_high
            is_surge = prev_vol > 0 and today_vol >= prev_vol * 3
            big_gain = today_pct_chg > 6

            row = {
                'symbol': symbol, 'st_code': st_code,
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

        except Exception:
            pass

    db.close()

    s1.sort(key=lambda x: x['pct_chg'], reverse=True)
    s2.sort(key=lambda x: x['pct_chg'], reverse=True)
    combined.sort(key=lambda x: x['pct_chg'], reverse=True)

    data = {
        'today': today, 'prev_day': prev_day,
        's1': s1, 's2': s2, 'combined': combined,
        'latest_date': latest_date,
    }

    _cache[cache_key] = (now, data)
    return data


def _query_signals(start_date='', end_date=''):
    """查询 st_daily_signal 表中的信号记录"""
    mdb = _connect_sm()
    mycsr = mdb.cursor(dictionary=True)

    # 检查表是否存在
    mycsr.execute("SHOW TABLES LIKE 'st_daily_signal'")
    if not mycsr.fetchone():
        mycsr.close(); mdb.close()
        return []

    sql = "SELECT * FROM st_daily_signal"
    params = []
    conditions = []

    if start_date:
        conditions.append("trade_date >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("trade_date <= %s")
        params.append(end_date)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY trade_date DESC, vol_ratio DESC"

    mycsr.execute(sql, tuple(params))
    records = mycsr.fetchall()
    mycsr.close(); mdb.close()
    return records


@app.get("/", response_class=HTMLResponse, tags=["page"])
async def signal_page(request: Request, start: str = '', end: str = ''):
    """放量涨幅筛选页面"""
    if not start:
        start = time.strftime("%Y%m%d", time.localtime())
    if not end:
        end = time.strftime("%Y%m%d", time.localtime())

    records = _query_signals(start, end)

    latest_date = records[0]['trade_date'] if records else None
    max_ratio = max((r['vol_ratio'] for r in records), default=None) if records else None

    return templates.TemplateResponse("signals.html", {
        "request": request,
        "records": records,
        "start_date": start,
        "end_date": end,
        "latest_date": latest_date,
        "max_ratio": max_ratio,
        "message": None,
        "msg_type": None,
    })


@app.post("/run-screener", response_class=HTMLResponse, tags=["action"])
async def run_screener(request: Request, start: str = Form(''), end: str = Form('')):
    """执行放量涨幅筛选并返回结果页面"""
    try:
        import stockPolicy as sp
        sp.createSignalTable()
        result = sp.getLiangJiaFangLiang(startDate=start, endDate=end)
        message = f"筛选完成，共找到 {len(result)} 只符合条件的股票"
        msg_type = "ok"
    except Exception as e:
        message = f"筛选执行出错: {e}"
        msg_type = "err"
        result = []

    if not start:
        start = time.strftime("%Y%m%d", time.localtime())
    if not end:
        end = time.strftime("%Y%m%d", time.localtime())

    records = _query_signals(start, end)
    latest_date = records[0]['trade_date'] if records else None
    max_ratio = max((r['vol_ratio'] for r in records), default=None) if records else None

    return templates.TemplateResponse("signals.html", {
        "request": request,
        "records": records,
        "start_date": start,
        "end_date": end,
        "latest_date": latest_date,
        "max_ratio": max_ratio,
        "message": message,
        "msg_type": msg_type,
    })


@app.get("/combined", response_class=HTMLResponse, tags=["page"])
async def combined_page(request: Request, date: str = ''):
    """跳空放量涨幅合并策略页面"""
    data = _run_combined_strategy(date)
    return templates.TemplateResponse("combined.html", {
        "request": request,
        "data": data,
        "date": date or data['today'],
    })
