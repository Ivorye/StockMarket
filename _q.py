import pymysql, datetime
db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
c = db.cursor()
c.execute("SELECT MAX(trade_date), COUNT(*) FROM st_daily")
print("st_daily MAX(trade_date), rows =", c.fetchone())
c.execute("SELECT trade_date, COUNT(DISTINCT ts_code) FROM st_daily WHERE trade_date>='20260920' GROUP BY trade_date ORDER BY trade_date")
for r in c.fetchall():
    print("  ", r)
c.execute("SELECT COUNT(*) FROM stocks")
print("stocks rows =", c.fetchone())
try:
    c.execute("SELECT MAX(trade_date) FROM st_daily_signal")
    print("st_daily_signal MAX =", c.fetchone())
except Exception as e:
    print("st_daily_signal ERR", e)
db.close()
print("today =", datetime.date.today())
