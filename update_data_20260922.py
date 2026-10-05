import pymysql, tushare as ts, time

TUSHARE_TOKEN = "4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9"
START_DATE = '20260909'
END_DATE = '20260922'
EXPECTED_DATES = ['20260909','20260910','20260911','20260914','20260915',
                  '20260916','20260917','20260918','20260921','20260922']

db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
cursor = db.cursor()
cursor.execute('SELECT symbol, st_code FROM stocks')
rows = cursor.fetchall()

def done_count(st_code):
    cursor.execute("SELECT COUNT(*) FROM st_daily WHERE ts_code=%s AND trade_date BETWEEN %s AND %s",
                   (st_code, START_DATE, END_DATE))
    return cursor.fetchone()[0]

missing = [r for r in rows if done_count(r[1]) < len(EXPECTED_DATES)]
print(f"total={len(rows)} need_update={len(missing)}")

pro = ts.pro_api(TUSHARE_TOKEN)
t0 = time.time()
inserted = 0
skipped = 0
sql = ("INSERT INTO st_daily(ts_code,symbol,trade_date,openp,high,low,closep,preclose,changes,pct_chg,vol,amount) "
       "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)")

for k, (symbol, st_code) in enumerate(missing):
    try:
        data = pro.daily(ts_code=st_code, start_date=START_DATE, end_date=END_DATE)
        if data is None or len(data) == 0:
            skipped += 1
            continue
        for i in range(len(data)):
            trade_date = data.iloc[i].trade_date
            cursor.execute("SELECT trade_date FROM st_daily WHERE ts_code=%s AND trade_date=%s", (st_code, trade_date))
            if cursor.fetchone() is None:
                try:
                    cursor.execute(sql, (
                        st_code, symbol, trade_date,
                        float(data.iloc[i].open), float(data.iloc[i].high), float(data.iloc[i].low),
                        float(data.iloc[i].close), float(data.iloc[i].pre_close), float(data.iloc[i].change),
                        float(data.iloc[i].pct_chg), float(data.iloc[i].vol), float(data.iloc[i].amount),
                    ))
                    inserted += 1
                except Exception as e:
                    print(f"插入异常 {symbol} {trade_date}: {e}")
                    db.rollback()
        db.commit()
        if (k + 1) % 100 == 0:
            print(f"processed {k+1}/{len(missing)}, inserted {inserted}, elapsed {time.time()-t0:.0f}s", flush=True)
    except Exception as e:
        err = str(e)
        if '频率' in err or 'exceeds' in err.lower():
            print(f"限频，暂停60s ({k+1}/{len(missing)})", flush=True)
            time.sleep(60)
            try:
                data = pro.daily(ts_code=st_code, start_date=START_DATE, end_date=END_DATE)
                if data is not None and len(data) > 0:
                    for i in range(len(data)):
                        trade_date = data.iloc[i].trade_date
                        cursor.execute("SELECT trade_date FROM st_daily WHERE ts_code=%s AND trade_date=%s", (st_code, trade_date))
                        if cursor.fetchone() is None:
                            cursor.execute(sql, (
                                st_code, symbol, trade_date,
                                float(data.iloc[i].open), float(data.iloc[i].high), float(data.iloc[i].low),
                                float(data.iloc[i].close), float(data.iloc[i].pre_close), float(data.iloc[i].change),
                                float(data.iloc[i].pct_chg), float(data.iloc[i].vol), float(data.iloc[i].amount),
                            ))
                            inserted += 1
                    db.commit()
            except Exception as e2:
                print(f"重试失败 {symbol}: {e2}", flush=True)
        else:
            print(f"查询异常 {symbol}: {e}", flush=True)

db.close()
print(f"完成！插入 {inserted} 条，跳过 {skipped}，耗时 {(time.time()-t0)/60:.1f} 分钟")
