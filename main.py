import time
import mysql.connector
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="StockMarket 筛选系统")
templates = Jinja2Templates(directory="templates")


def _connect_sm():
    return mysql.connector.connect(host="localhost", user="root", passwd="P@ssw0rd", database='stockshare')


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
