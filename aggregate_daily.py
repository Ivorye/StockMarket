import mysql.connector

mdb = mysql.connector.connect(host='localhost', user='root', passwd='P@ssw0rd', database='stockshare')
c = mdb.cursor()

# 获取所有gp*表名
c.execute("SHOW TABLES LIKE 'gp%'")
tables = [t[0] for t in c.fetchall() if '_seq' not in t[0]]
print(f'Total gp tables: {len(tables)}')

insert_template = """INSERT IGNORE INTO st_daily 
    (trade_date, st_code, openPrice, highest, lowest, closePrice, pre_close, changedValue, pct_chg, vol, amount)
    SELECT trade_date, %s, openp, high, low, closep, preclose, changes, pct_chg, vol, amount 
    FROM `{table}`"""

total = 0
for i, tbl in enumerate(tables):
    symbol = tbl[2:]
    c.execute('SELECT st_code FROM stocks WHERE symbol=%s', (symbol,))
    row = c.fetchone()
    if not row:
        continue
    st_code = row[0]

    try:
        insert_sql = insert_template.format(table=tbl)
        c.execute(insert_sql, (st_code,))
        total += c.rowcount
    except Exception as e:
        print(f'Error {tbl}: {e}')

    if (i + 1) % 500 == 0:
        mdb.commit()
        print(f'{i + 1} tables processed, {total} rows inserted')

mdb.commit()
print(f'Done: {len(tables)} tables, {total} total rows inserted')

c.execute('SELECT COUNT(*) FROM st_daily')
print(f'st_daily final count: {c.fetchone()[0]}')

c.execute('SELECT * FROM st_daily ORDER BY trade_date DESC LIMIT 5')
for row in c.fetchall():
    print(row)

c.close()
mdb.close()
