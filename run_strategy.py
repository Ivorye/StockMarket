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

# 开始筛选
result = []
for symbol, st_code in stocks:
    table = '`gp%s`' % symbol
    try:
        # 查询今天和前天的数据
        cursor.execute('SELECT trade_date, openp, high, low, closep, pct_chg, vol FROM %s WHERE trade_date IN (%%s, %%s) ORDER BY trade_date' % table, (prev_day, today))
        rows = cursor.fetchall()
        
        if len(rows) == 2:
            prev_data = rows[0]
            today_data = rows[1]
            
            pct_chg = today_data[5]
            vol_today = today_data[6]
            vol_prev = prev_data[6]
            
            # 放量>=3倍 且 涨幅>6%
            if vol_prev > 0 and vol_today >= vol_prev * 3 and pct_chg > 6:
                # 排除科创板(688)、ST、*ST
                if symbol.startswith('688'):
                    continue
                result.append({
                    'symbol': symbol,
                    'st_code': st_code,
                    'pct_chg': pct_chg,
                    'vol_ratio': round(vol_today / vol_prev, 2)
                })
    except Exception as e:
        pass  # 跳过异常

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
