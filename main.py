import time
import os
import csv
import re
import pymysql
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="StockMarket 筛选系统")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def _init_db():
    import stockPolicy as sp
    sp.createSignalTable()


# 内存缓存: {cache_key: (timestamp, data)}
_cache = {}
_CACHE_TTL = 1800  # 30分钟
_DB_TIMEOUT_SECONDS = 15


def _connect_db():
    return pymysql.connect(
        host='localhost', user='root', password='P@ssw0rd', database='stockshare',
        connect_timeout=_DB_TIMEOUT_SECONDS,
        read_timeout=_DB_TIMEOUT_SECONDS,
        write_timeout=_DB_TIMEOUT_SECONDS,
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

    for row_data in cursor.fetchall():
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
            "SELECT d.ts_code,COALESCE(s.fullname,''),d.closep FROM st_daily d "
            "LEFT JOIN stocks s ON s.st_code=d.ts_code "
            f"WHERE d.trade_date IN ({placeholders}) AND d.symbol NOT LIKE '688%%' "
            "ORDER BY d.ts_code,d.trade_date", tuple(smooth_dates))
        grouped = {}
        for st_code, fullname, closep in cursor.fetchall():
            item = grouped.setdefault(st_code, {'name': fullname, 'closes': []})
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


@app.get("/", response_class=HTMLResponse, tags=["page"])
@app.get("/combined", response_class=HTMLResponse, tags=["page"])
async def combined_page(request: Request, date: str = ''):
    """跳空放量涨幅合并策略页面"""
    data = _run_combined_strategy(date)
    return templates.TemplateResponse("combined.html", {
        "request": request,
        "data": data,
        "backtest": _load_backtest_results(),
        "date": date or data['today'],
    })


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
            "COALESCE(s.fullname,'') FROM st_daily d "
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
