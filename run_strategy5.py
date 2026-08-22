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

# 跳空上涨过策略：
# 条件：
# 1. 期间收盘价从起点到现在涨幅超30%
# 2. 某一天出现跳空缺口（当日最低 > 前日最高）
# 3. 跳空当天放量（成交量 > 前日2.5倍）
startDate = '20250814'
endDate = latest_date
print(f'分析区间: {startDate} - {endDate}')

result = []
for symbol, st_code in stocks:
    # 排除科创板(688)
    if symbol.startswith('688'):
        continue
    table = '`gp%s`' % symbol
    try:
        # 查询区间内所有交易数据
        cursor.execute('''SELECT trade_date, openp, high, low, closep, pct_chg, vol 
                         FROM %s WHERE trade_date >= %s AND trade_date <= %s 
                         ORDER BY trade_date''' % (table, '%s', '%s'), (startDate, endDate))
        rows = cursor.fetchall()
        
        if len(rows) < 3:
            continue
        
        # 检查整体涨幅是否超30%
        first_close = rows[0][4]
        last_close = rows[-1][4]
        
        if first_close <= 0:
            continue
            
        total_gain = (last_close - first_close) / first_close
        if total_gain < 0.3:
            continue
        
        # 检查是否有跳空上涨日
        has_gap = False
        gap_date = None
        gap_info = None
        
        for i in range(1, len(rows)):
            prev = rows[i-1]
            curr = rows[i]
            
            prev_high = prev[2]
            prev_vol = prev[6]
            curr_low = curr[3]
            curr_vol = curr[6]
            curr_close = curr[4]
            
            # 跳空条件：当日最低 > 前日最高，且放量>=2.5倍
            if curr_low > prev_high and prev_vol > 0 and curr_vol >= prev_vol * 2.5:
                has_gap = True
                gap_date = curr[0]
                gap_info = {
                    'gap_low': curr_low,
                    'prev_high': prev_high,
                    'gap_size': round(curr_low - prev_high, 2),
                    'vol_ratio': round(curr_vol / prev_vol, 2)
                }
                break
        
        if has_gap:
            result.append({
                'symbol': symbol,
                'st_code': st_code,
                'gain_pct': round(total_gain * 100, 2),
                'gap_date': gap_date,
                'gap_size': gap_info['gap_size'],
                'vol_ratio': gap_info['vol_ratio'],
                'current_close': last_close
            })
    except Exception as e:
        pass

db.close()

# 按涨幅排序
result.sort(key=lambda x: x['gain_pct'], reverse=True)

# 保存结果到文件
filename = f'跳空上涨过_{latest_date}.txt'
with open(filename, 'w', encoding='utf-8') as f:
    f.write(f'跳空上涨过筛选结果\n')
    f.write(f'分析区间: {startDate} - {endDate}\n')
    f.write(f'条件: 期间涨幅>=30% 且 出现过跳空放量缺口\n')
    f.write('-' * 90 + '\n')
    for stock in result:
        line = f"{stock['st_code']}  涨幅:{stock['gain_pct']}%  跳空日:{stock['gap_date']}  缺口:{stock['gap_size']}  量比:{stock['vol_ratio']}  当前价:{stock['current_close']}"
        f.write(line + '\n')

# 输出结果
print(f'\n筛选完成，共 {len(result)} 只股票')
print(f'结果已保存到: {filename}')
print('-' * 90)
for stock in result[:50]:
    print(f"{stock['st_code']}  涨幅:{stock['gain_pct']}%  跳空日:{stock['gap_date']}  缺口:{stock['gap_size']}  量比:{stock['vol_ratio']}  当前价:{stock['current_close']}")

if len(result) > 50:
    print(f'... 还有 {len(result) - 50} 只股票，详见文件')
