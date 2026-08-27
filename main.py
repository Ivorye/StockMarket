import time
import os
import csv
import pymysql
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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


def _eastmoney_url(st_code: str) -> str:
    """根据股票代码生成东方财富链接，如 000001.SZ -> https://quote.eastmoney.com/sz000001.html"""
    parts = st_code.split('.')
    if len(parts) == 2:
        symbol, exchange = parts[0], parts[1].lower()
        return f'https://quote.eastmoney.com/{exchange}{symbol}.html'
    return '#'


templates.env.globals['eastmoney_url'] = _eastmoney_url


def _save_signals(rows, strategy, trade_date):
    """将策略筛选结果写入 st_daily_signal 表和 CSV 文件"""
    if not rows:
        return
    try:
        db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
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

    # 将策略结果写入 st_daily_signal 表
    _save_signals(s1, '放量涨幅', today)
    _save_signals(s2, '跳空缺口', today)
    _save_signals(combined, '跳空放量涨幅', today)

    data = {
        'today': today, 'prev_day': prev_day,
        's1': s1, 's2': s2, 'combined': combined,
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
        "date": date or data['today'],
    })
