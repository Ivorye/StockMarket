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

# 开始筛选：向上跳空缺口
# 条件：今日最低价 > 昨日最高价，且今日收盘 > 昨日收盘
result = []
for symbol, st_code in stocks:
    # 排除科创板(688)
    if symbol.startswith('688'):
        continue
    table = '`gp%s`' % symbol
    try:
        # 查询今天和前天的数据
        cursor.execute('''SELECT trade_date, openp, high, low, closep, pct_chg, vol 
                         FROM %s WHERE trade_date IN (%%s, %%s) ORDER BY trade_date''' % table, (prev_day, today))
        rows = cursor.fetchall()
        
        if len(rows) == 2:
            prev_data = rows[0]  # 前天
            today_data = rows[1]  # 今天
            
            # 前天: trade_date, openp, high, low, closep, pct_chg, vol
            prev_high = prev_data[2]
            prev_close = prev_data[4]
            prev_vol = prev_data[6]
            
            # 今天
            today_low = today_data[3]
            today_close = today_data[4]
            today_pct_chg = today_data[5]
            today_vol = today_data[6]
            
            # 向上跳空缺口：今日最低 > 昨日最高
            if today_low > prev_high and today_close > prev_close:
                vol_ratio = round(today_vol / prev_vol, 2) if prev_vol > 0 else 0
                result.append({
                    'symbol': symbol,
                    'st_code': st_code,
                    'pct_chg': today_pct_chg,
                    'vol_ratio': vol_ratio,
                    'gap': round(today_low - prev_high, 2)
                })
    except Exception as e:
        pass  # 跳过异常

db.close()

# 保存结果到文件
filename = f'向上跳空缺口_{today}.txt'
with open(filename, 'w', encoding='utf-8') as f:
    f.write(f'向上跳空缺口筛选结果\n')
    f.write(f'筛选日期: {today} vs {prev_day}\n')
    f.write(f'条件: 今日最低价 > 昨日最高价 且 今日收盘 > 昨日收盘\n')
    f.write('-' * 70 + '\n')
    for stock in result:
        line = f"{stock['st_code']}  涨幅:{stock['pct_chg']:.2f}%  量比:{stock['vol_ratio']}  缺口:{stock['gap']}"
        f.write(line + '\n')

# 输出结果
print(f'\n筛选完成，共 {len(result)} 只股票')
print(f'结果已保存到: {filename}')
print('-' * 70)
for stock in result:
    print(f"{stock['st_code']}  涨幅:{stock['pct_chg']:.2f}%  量比:{stock['vol_ratio']}  缺口:{stock['gap']}")
