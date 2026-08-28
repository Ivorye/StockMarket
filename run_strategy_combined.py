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

# 跳空放量涨幅策略：
# 条件（同时满足）：
# 1. 向上跳空缺口：今日最低价 > 昨日最高价
# 2. 放量：今日成交量 >= 昨日成交量的 3 倍
# 3. 大涨：今日涨幅 > 6%
cursor.execute('''SELECT d.symbol, s.st_code, d.openp, d.high, d.low, d.closep,
                         d.pct_chg, d.vol, p.vol, ROUND(d.vol / p.vol, 2),
                         ROUND(d.low - p.high, 2), p.high, p.closep
                  FROM st_daily d
                  JOIN st_daily p ON p.ts_code = d.ts_code AND p.trade_date = %s
                  JOIN stocks s ON s.st_code = d.ts_code
                  WHERE d.trade_date = %s AND d.symbol NOT LIKE '688%%'
                    AND d.low > p.high AND p.vol > 0
                    AND d.vol >= p.vol * 3 AND d.pct_chg > 6''', (prev_day, today))
keys = ('symbol', 'st_code', 'openp', 'high', 'low', 'closep', 'pct_chg',
        'vol', 'prev_vol', 'vol_ratio', 'gap_size', 'prev_high', 'prev_close')
result = [dict(zip(keys, row)) for row in cursor.fetchall()]

db.close()

# 按涨幅排序
result.sort(key=lambda x: x['pct_chg'], reverse=True)

# 保存结果到文件
filename = f'跳空放量涨幅_{today}.txt'
with open(filename, 'w', encoding='utf-8') as f:
    f.write(f'跳空放量涨幅筛选结果\n')
    f.write(f'筛选日期: {today} vs {prev_day}\n')
    f.write(f'条件: 跳空缺口(今低>昨高) + 放量>=3倍 + 涨幅>6%\n')
    f.write('-' * 100 + '\n')
    for stock in result:
        line = (f"{stock['st_code']}  涨幅:{stock['pct_chg']:.2f}%  量比:{stock['vol_ratio']}  "
                f"缺口:{stock['gap_size']}  今开:{stock['openp']}  今高:{stock['high']}  "
                f"今低:{stock['low']}  今收:{stock['closep']}  "
                f"昨高:{stock['prev_high']}  昨收:{stock['prev_close']}")
        f.write(line + '\n')

# 输出结果
print(f'\n筛选完成，共 {len(result)} 只股票')
print(f'结果已保存到: {filename}')
print('-' * 100)
for stock in result:
    print(f"{stock['st_code']}  涨幅:{stock['pct_chg']:.2f}%  量比:{stock['vol_ratio']}  "
          f"缺口:{stock['gap_size']}  今开:{stock['openp']}  今高:{stock['high']}  "
          f"今低:{stock['low']}  今收:{stock['closep']}  "
          f"昨高:{stock['prev_high']}  昨收:{stock['prev_close']}")
