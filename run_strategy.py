import pymysql

# 连接数据库
db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
cursor = db.cursor()

# 获取股票列表
cursor.execute('SELECT symbol, st_code FROM stocks')
stocks = cursor.fetchall()
print(f'共 {len(stocks)} 只股票')

# 找到最新的交易日期
cursor.execute('SELECT MAX(trade_date) FROM st_daily')
latest_date = cursor.fetchone()[0]
print(f'最新交易日期: {latest_date}')

# 获取前一个交易日
cursor.execute('SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT 2')
dates = cursor.fetchall()
if len(dates) < 2:
    print('交易数据不足')
    db.close()
    exit()

today = dates[0][0]
prev_day = dates[1][0]
print(f'筛选日期: {today} vs {prev_day}')

# 开始筛选
cursor.execute('''SELECT d.symbol, s.st_code, d.pct_chg,
                         ROUND(d.vol / p.vol, 2) AS vol_ratio
                  FROM st_daily d
                  JOIN st_daily p ON p.ts_code = d.ts_code AND p.trade_date = %s
                  JOIN stocks s ON s.st_code = d.ts_code
                  WHERE d.trade_date = %s
                    AND d.symbol NOT LIKE '688%%'
                    AND p.vol > 0 AND d.vol >= p.vol * 3 AND d.pct_chg > 6''',
               (prev_day, today))
result = [dict(symbol=row[0], st_code=row[1], pct_chg=row[2], vol_ratio=row[3])
          for row in cursor.fetchall()]

db.close()

# 保存结果到文件
filename = f'放量涨幅筛选_{today}.txt'
with open(filename, 'w', encoding='utf-8') as f:
    f.write(f'放量涨幅筛选结果\n')
    f.write(f'筛选日期: {today} vs {prev_day}\n')
    f.write(f'条件: 成交量>=前日3倍 且 涨幅>6%\n')
    f.write('-' * 60 + '\n')
    for stock in result:
        line = f"{stock['st_code']}  涨幅:{stock['pct_chg']:.2f}%  量比:{stock['vol_ratio']}"
        f.write(line + '\n')

# 输出结果
print(f'\n筛选完成，共 {len(result)} 只股票')
print(f'结果已保存到: {filename}')
print('-' * 60)
for stock in result:
    print(f"{stock['st_code']}  涨幅:{stock['pct_chg']:.2f}%  量比:{stock['vol_ratio']}")
