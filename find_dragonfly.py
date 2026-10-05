# 蜻蜓点水形态筛选器
# 条件：
# 1. 蜻蜓点水K线：下影线>=2倍实体，实体很小，上影线短
# 2. 当天缩量（成交量 < 前4日均量）
# 3. 次日高开或收阳，且收盘价不跌破蜻蜓点水日最低点

import mysql.connector
from collections import defaultdict

db = mysql.connector.connect(host='localhost', user='root', passwd='P@ssw0rd', database='stockshare', connection_timeout=10)
cursor = db.cursor()

# 获取最近15个交易日（覆盖2周）
cursor.execute('SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT 15')
dates = sorted([r[0] for r in cursor.fetchall()])
two_week_start = dates[0]

print('最近交易日范围:', two_week_start, '~', dates[-1])
print()

# 获取20个交易日的数据（含前几天用于计算均量）
cursor.execute('SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT 20')
all_dates = sorted([r[0] for r in cursor.fetchall()])

# 批量读取
cursor.execute(
    'SELECT d.ts_code, d.trade_date, d.openp, d.high, d.low, d.closep, d.vol '
    'FROM st_daily d '
    'WHERE d.trade_date >= %s '
    'AND d.symbol NOT LIKE "688%%" '
    'ORDER BY d.ts_code, d.trade_date',
    (all_dates[0],)
)

stock_data = defaultdict(list)
for ts_code, trade_date, openp, high, low, closep, vol in cursor.fetchall():
    stock_data[ts_code].append({
        'date': trade_date, 'open': float(openp), 'high': float(high),
        'low': float(low), 'close': float(closep), 'vol': float(vol)
    })

# 获取股票名称
cursor.execute('SELECT st_code, COALESCE(NULLIF(name,""), fullname) FROM stocks')
name_map = dict(cursor.fetchall())
cursor.close()
db.close()

def is_st(name):
    if not name:
        return False
    return name.startswith('ST') or name.startswith('*ST')

print('扫描', len(stock_data), '只股票...')

results = []

for ts_code, rows in stock_data.items():
    name = name_map.get(ts_code, '')
    if is_st(name):
        continue

    date_idx = {r['date']: i for i, r in enumerate(rows)}

    for i, row in enumerate(rows):
        d = row['date']
        if d < two_week_start:
            continue

        o, h, l, c, v = row['open'], row['high'], row['low'], row['close'], row['vol']
        body = abs(c - o)
        lower_shadow = min(o, c) - l
        upper_shadow = h - max(o, c)
        k_range = h - l

        if k_range <= 0:
            continue

        # 蜻蜓点水形态：下影线 >= 2倍实体，实体很小，上影线短
        if body > o * 0.01:
            continue
        if lower_shadow < 2 * body:
            continue
        if upper_shadow > body:
            continue

        # 缩量：与前4天平均成交量比
        if i < 4:
            continue
        avg_vol = sum(rows[j]['vol'] for j in range(i-4, i)) / 4
        if avg_vol <= 0 or v >= avg_vol:
            continue

        # 第二天
        if i + 1 >= len(rows):
            continue
        next_row = rows[i + 1]

        n_o, n_h, n_l, n_c = next_row['open'], next_row['high'], next_row['low'], next_row['close']

        # 次日高开或收阳
        gap_up = n_o > c
        bullish = n_c > n_o
        if not (gap_up or bullish):
            continue

        # 次日收盘不跌破蜻蜓点水日最低点
        if n_c < l:
            continue

        vol_ratio = round(v / avg_vol, 2)
        shadow_ratio = round(lower_shadow / body, 1) if body > 0 else 999
        results.append({
            'code': ts_code,
            'name': name,
            'pattern_date': d,
            'next_date': next_row['date'],
            'pattern_close': c,
            'pattern_low': l,
            'next_close': n_c,
            'vol_ratio': vol_ratio,
            'shadow_ratio': shadow_ratio,
        })

results.sort(key=lambda x: x['pattern_date'], reverse=True)

print()
print('=' * 80)
print('蜻蜓点水筛选结果（最近两周内，共 %d 只）' % len(results))
print('=' * 80)
for r in results:
    ok = 'OK' if r['next_close'] >= r['pattern_low'] else 'FAIL'
    print('%s %-10s  蜻蜓日:%s  收盘:%.2f  最低:%.2f' % (
        r['code'], r['name'], r['pattern_date'], r['pattern_close'], r['pattern_low']))
    print('  下影线/实体:%sx  缩量比:%s' % (r['shadow_ratio'], r['vol_ratio']))
    print('  次日:%s  收盘:%.2f  (不破低点 %s)' % (r['next_date'], r['next_close'], ok))
    print()
