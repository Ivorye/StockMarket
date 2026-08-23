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

# 翻倍股策略：从startDate到endDate涨幅超过multiple倍
# 这里用最近1年作为观察期
startDate = '20250814'
endDate = latest_date
multiple = 1.0  # 涨幅1倍 = 翻倍

print(f'筛选区间: {startDate} - {endDate}')
print(f'条件: 期间涨幅 >= {multiple * 100}%')

result = []
for symbol, st_code in stocks:
    # 排除科创板(688)
    if symbol.startswith('688'):
        continue
    table = '`gp%s`' % symbol
    try:
        # 查询起始日和结束日的收盘价
        cursor.execute('''SELECT trade_date, closep FROM %s 
                         WHERE trade_date IN (%s, %s) 
                         ORDER BY trade_date''' % (table, '%s', '%s'), (startDate, endDate))
        rows = cursor.fetchall()
        
        if len(rows) == 2:
            start_price = rows[0][1]
            end_price = rows[1][1]
            
            if start_price > 0:
                gain = (end_price - start_price) / start_price
                if gain >= multiple:
                    result.append({
                        'symbol': symbol,
                        'st_code': st_code,
                        'start_price': start_price,
                        'end_price': end_price,
                        'gain_pct': round(gain * 100, 2)
                    })
    except Exception as e:
        # 如果精确日期没有数据，尝试找最近的交易日
        try:
            cursor.execute('''SELECT trade_date, closep FROM %s 
                             WHERE trade_date >= %s ORDER BY trade_date ASC LIMIT 1''' % table, (startDate,))
            row_start = cursor.fetchone()
            
            cursor.execute('''SELECT trade_date, closep FROM %s 
                             WHERE trade_date <= %s ORDER BY trade_date DESC LIMIT 1''' % table, (endDate,))
            row_end = cursor.fetchone()
            
            if row_start and row_end:
                start_price = row_start[1]
                end_price = row_end[1]
                
                if start_price > 0:
                    gain = (end_price - start_price) / start_price
                    if gain >= multiple:
                        result.append({
                            'symbol': symbol,
                            'st_code': st_code,
                            'start_price': start_price,
                            'end_price': end_price,
                            'gain_pct': round(gain * 100, 2)
                        })
        except:
            pass

db.close()

# 按涨幅排序
result.sort(key=lambda x: x['gain_pct'], reverse=True)

# 保存结果到文件
filename = f'翻倍股_{latest_date}.txt'
with open(filename, 'w', encoding='utf-8') as f:
    f.write(f'翻倍股筛选结果\n')
    f.write(f'筛选区间: {startDate} - {endDate}\n')
    f.write(f'条件: 期间涨幅 >= {multiple * 100}%\n')
    f.write('-' * 80 + '\n')
    for stock in result:
        line = f"{stock['st_code']}  起始价:{stock['start_price']}  当前价:{stock['end_price']}  涨幅:{stock['gain_pct']}%"
        f.write(line + '\n')

# 输出结果
print(f'\n筛选完成，共 {len(result)} 只股票')
print(f'结果已保存到: {filename}')
print('-' * 80)
for stock in result[:50]:  # 只显示前50只
    print(f"{stock['st_code']}  起始价:{stock['start_price']}  当前价:{stock['end_price']}  涨幅:{stock['gain_pct']}%")

if len(result) > 50:
    print(f'... 还有 {len(result) - 50} 只股票，详见文件')
