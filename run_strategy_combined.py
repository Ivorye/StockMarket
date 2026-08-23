import pymysql

# 连接数据库
db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
cursor = db.cursor()

# 获取股票列表
cursor.execute('SELECT symbol, st_code FROM stocks')
stocks = cursor.fetchall()
print(f'共 {len(stocks)} 只股票')

# 找到最新的交易日期
cursor.execute('SELECT MAX(trade_date) FROM `gp000001`')
latest_date = cursor.fetchone()[0]
print(f'最新交易日期: {latest_date}')

# 获取前一个交易日
cursor.execute('SELECT DISTINCT trade_date FROM `gp000001` ORDER BY trade_date DESC LIMIT 2')
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
result = []
for symbol, st_code in stocks:
    # 排除科创板(688)
    if symbol.startswith('688'):
        continue
    table = '`gp%s`' % symbol
    try:
        cursor.execute('''SELECT trade_date, openp, high, low, closep, pct_chg, vol
                         FROM %s WHERE trade_date IN (%%s, %%s) ORDER BY trade_date''' % table, (prev_day, today))
        rows = cursor.fetchall()

        if len(rows) == 2:
            prev_data = rows[0]
            today_data = rows[1]

            prev_high = prev_data[2]
            prev_close = prev_data[4]
            prev_vol = prev_data[6]

            today_low = today_data[3]
            today_close = today_data[4]
            today_pct_chg = today_data[5]
            today_vol = today_data[6]

            # 三个条件同时满足
            has_gap = today_low > prev_high           # 跳空缺口
            is_surge = prev_vol > 0 and today_vol >= prev_vol * 3  # 放量>=3倍
            big_gain = today_pct_chg > 6              # 涨幅>6%

            if has_gap and is_surge and big_gain:
                vol_ratio = round(today_vol / prev_vol, 2)
                gap_size = round(today_low - prev_high, 2)
                result.append({
                    'symbol': symbol,
                    'st_code': st_code,
                    'openp': today_data[1],
                    'high': today_data[2],
                    'low': today_data[3],
                    'closep': today_close,
                    'pct_chg': today_pct_chg,
                    'vol': today_vol,
                    'prev_vol': prev_vol,
                    'vol_ratio': vol_ratio,
                    'gap_size': gap_size,
                    'prev_high': prev_high,
                    'prev_close': prev_close
                })
    except Exception as e:
        pass

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
