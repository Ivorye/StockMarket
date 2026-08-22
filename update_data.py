import pymysql, tushare as ts, time

TUSHARE_TOKEN = "4d47c02a8bb025881c9dd9e3c36d25139ab5b429a73353e566fc02a9"

db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
cursor = db.cursor()
cursor.execute('SELECT symbol, st_code FROM stocks')
rows = cursor.fetchall()
print(f"共 {len(rows)} 只股票，开始更新 20260815 ~ 20260817")

pro = ts.pro_api(TUSHARE_TOKEN)
t0 = time.time()
total = len(rows)
inserted = 0
skipped = 0

for k, (symbol, st_code) in enumerate(rows):
    try:
        data = pro.daily(ts_code=st_code, start_date='20260815', end_date='20260817')
        if data is None or len(data) == 0:
            skipped += 1
            continue
        table = '`gp%s`' % symbol
        for i in range(len(data)):
            sql0 = "SELECT trade_date FROM %s WHERE trade_date=%%s" % table
            sql = ("INSERT INTO %s(trade_date,openp,high,low,closep,preclose,changes,pct_chg,vol,amount) "
                   "VALUES(%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s)" % table)
            result = cursor.execute(sql0, (data.iloc[i].trade_date,))
            if result == 0:
                try:
                    cursor.execute(sql, (
                        data.iloc[i].trade_date,
                        float(data.iloc[i].open),
                        float(data.iloc[i].high),
                        float(data.iloc[i].low),
                        float(data.iloc[i].close),
                        float(data.iloc[i].pre_close),
                        float(data.iloc[i].change),
                        float(data.iloc[i].pct_chg),
                        float(data.iloc[i].vol),
                        float(data.iloc[i].amount),
                    ))
                    inserted += 1
                except Exception as e:
                    print(f"插入异常 {symbol} {data.iloc[i].trade_date}: {e}")
                    db.rollback()
        db.commit()
        if (k + 1) % 100 == 0:
            elapsed = time.time() - t0
            print(f"已处理 {k+1}/{total}，插入 {inserted} 条，耗时 {elapsed:.0f}s")
    except Exception as e:
        err = str(e)
        if '频率' in err or 'exceeds' in err.lower():
            print(f"API限频，暂停60秒后继续... ({k+1}/{total})")
            time.sleep(60)
            # 重试一次
            try:
                data = pro.daily(ts_code=st_code, start_date='20260815', end_date='20260817')
                if data is not None and len(data) > 0:
                    table = '`gp%s`' % symbol
                    for i in range(len(data)):
                        sql0 = "SELECT trade_date FROM %s WHERE trade_date=%%s" % table
                        sql = ("INSERT INTO %s(trade_date,openp,high,low,closep,preclose,changes,pct_chg,vol,amount) "
                               "VALUES(%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s,%%s)" % table)
                        result = cursor.execute(sql0, (data.iloc[i].trade_date,))
                        if result == 0:
                            try:
                                cursor.execute(sql, (
                                    data.iloc[i].trade_date,
                                    float(data.iloc[i].open), float(data.iloc[i].high),
                                    float(data.iloc[i].low), float(data.iloc[i].close),
                                    float(data.iloc[i].pre_close), float(data.iloc[i].change),
                                    float(data.iloc[i].pct_chg), float(data.iloc[i].vol),
                                    float(data.iloc[i].amount),
                                ))
                                inserted += 1
                            except Exception as e2:
                                print(f"重试插入异常 {symbol}: {e2}")
                                db.rollback()
                    db.commit()
            except Exception as e2:
                print(f"重试失败 {symbol}: {e2}")
        else:
            print(f"查询异常 {symbol}: {e}")

db.close()
elapsed = time.time() - t0
print(f"\n完成！共插入 {inserted} 条新记录，跳过 {skipped} 只无新数据，耗时 {elapsed/60:.1f} 分钟")
