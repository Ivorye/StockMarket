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

# 获取最近5个交易日
cursor.execute('SELECT DISTINCT trade_date FROM `gp000001` ORDER BY trade_date DESC LIMIT 5')
dates = cursor.fetchall()
if len(dates) < 5:
    print('交易数据不足，需要至少5个交易日')
    db.close()
    exit()

# dates[0]=最新, dates[1]=前1天, dates[2]=前2天, dates[3]=前3天, dates[4]=前4天
print(f'分析日期: {[d[0] for d in dates]}')

# 巨量上涨策略：
# 条件：某一天(A日)成交量>=前日2倍 且 涨幅>4%
# A日之后2-3天量缩调整，振幅在3%以内
# 当前价格高于A日收盘价
multiple = 2  # 量比倍数

result = []
for symbol, st_code in stocks:
    # 排除科创板(688)
    if symbol.startswith('688'):
        continue
    table = '`gp%s`' % symbol
    try:
        # 查询最近5天的数据
        date_list = [d[0] for d in dates]
        placeholders = ','.join(['%s'] * 5)
        cursor.execute('''SELECT trade_date, openp, high, low, closep, pct_chg, vol 
                         FROM %s WHERE trade_date IN (%s) ORDER BY trade_date DESC''' % (table, placeholders), date_list)
        rows = cursor.fetchall()
        
        if len(rows) >= 4:
            # rows[0]=最新日, rows[1]=前1天, rows[2]=前2天, rows[3]=前3天
            # 可能还有 rows[4]=前4天
            
            latest = rows[0]  # 最新日
            
            # 检查前1天、前2天、前3天是否有巨量上涨日
            for check_idx in [1, 2, 3]:
                if check_idx >= len(rows):
                    continue
                    
                surge_day = rows[check_idx]  # 候选巨量上涨日
                
                # surge_day的前一日
                prev_idx = check_idx + 1
                if prev_idx >= len(rows):
                    continue
                prev_day = rows[prev_idx]
                
                # 巨量上涨条件：成交量>=前日2倍 且 涨幅>4%
                if prev_day[6] > 0 and surge_day[6] >= prev_day[6] * multiple and surge_day[5] > 4:
                    # 检查巨量上涨日之后的日子是否缩量调整
                    # check_idx之前的几天（更靠近最新日）应该缩量
                    is_consolidation = True
                    for adj_idx in range(check_idx - 1, -1, -1):
                        adj_day = rows[adj_idx]
                        # 振幅 = (最高-最低)/收盘 * 100
                        amplitude = (adj_day[1] - adj_day[3]) / adj_day[4] * 100 if adj_day[4] > 0 else 0
                        # 调整日涨幅应在-3%到3%之间
                        if abs(adj_day[5]) > 3:
                            is_consolidation = False
                            break
                    
                    # 当前价格（最新日收盘）> 巨量上涨日收盘
                    if is_consolidation and latest[4] > surge_day[4]:
                        vol_ratio = round(surge_day[6] / prev_day[6], 2)
                        result.append({
                            'symbol': symbol,
                            'st_code': st_code,
                            'surge_date': surge_day[0],
                            'surge_pct': surge_day[5],
                            'vol_ratio': vol_ratio,
                            'current_close': latest[4],
                            'surge_close': surge_day[4]
                        })
                        break  # 找到一个就够了
    except Exception as e:
        pass  # 跳过异常

db.close()

# 保存结果到文件
filename = f'巨量上涨_{latest_date}.txt'
with open(filename, 'w', encoding='utf-8') as f:
    f.write(f'巨量上涨筛选结果\n')
    f.write(f'最新交易日: {latest_date}\n')
    f.write(f'条件: 某日成交量>=前日{multiple}倍 且 涨幅>4%，之后缩量调整，当前价格>巨量日收盘\n')
    f.write('-' * 80 + '\n')
    for stock in result:
        line = f"{stock['st_code']}  巨量日:{stock['surge_date']}  涨幅:{stock['surge_pct']:.2f}%  量比:{stock['vol_ratio']}  当前价:{stock['current_close']}"
        f.write(line + '\n')

# 输出结果
print(f'\n筛选完成，共 {len(result)} 只股票')
print(f'结果已保存到: {filename}')
print('-' * 80)
for stock in result:
    print(f"{stock['st_code']}  巨量日:{stock['surge_date']}  涨幅:{stock['surge_pct']:.2f}%  量比:{stock['vol_ratio']}  当前价:{stock['current_close']}")
