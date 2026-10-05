# 蜻蜓点水汇总
import mysql.connector
from collections import defaultdict, Counter

db = mysql.connector.connect(host='localhost', user='root', passwd='P@ssw0rd', database='stockshare', connection_timeout=10)
cursor = db.cursor()
cursor.execute('SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT 15')
dates = sorted([r[0] for r in cursor.fetchall()])
two_week_start = dates[0]

cursor.execute('SELECT DISTINCT trade_date FROM st_daily ORDER BY trade_date DESC LIMIT 20')
all_dates = sorted([r[0] for r in cursor.fetchall()])

cursor.execute(
    "SELECT d.ts_code, d.trade_date, d.openp, d.high, d.low, d.closep, d.vol "
    "FROM st_daily d WHERE d.trade_date >= %s AND d.symbol NOT LIKE '688%%' "
    "ORDER BY d.ts_code, d.trade_date", (all_dates[0],))

stock_data = defaultdict(list)
for ts_code, trade_date, openp, high, low, closep, vol in cursor.fetchall():
    stock_data[ts_code].append({
        'date': trade_date, 'open': float(openp), 'high': float(high),
        'low': float(low), 'close': float(closep), 'vol': float(vol)
    })

cursor.execute('SELECT st_code, COALESCE(NULLIF(name,""), fullname) FROM stocks')
name_map = dict(cursor.fetchall())
cursor.close(); db.close()

def is_st(n): return n and (n.startswith('ST') or n.startswith('*ST'))

results = []
for ts_code, rows in stock_data.items():
    name = name_map.get(ts_code, '')
    if is_st(name): continue
    for i, row in enumerate(rows):
        if row['date'] < two_week_start: continue
        o, h, l, c, v = row['open'], row['high'], row['low'], row['close'], row['vol']
        body = abs(c - o); lower = min(o, c) - l; upper = h - max(o, c)
        if h - l <= 0 or body > o * 0.01 or lower < 2 * body or upper > body or i < 4: continue
        avg_v = sum(rows[j]['vol'] for j in range(i-4, i)) / 4
        if avg_v <= 0 or v >= avg_v: continue
        if i + 1 >= len(rows): continue
        nr = rows[i + 1]
        no, nc = nr['open'], nr['close']
        if not (no > c or nc > no): continue
        if nc < l: continue
        vr = round(v / avg_v, 2)
        sr = round(lower / body, 1) if body > 0 else 999
        results.append({
            'code': ts_code, 'name': name, 'pd': row['date'], 'nd': nr['date'],
            'pc': c, 'pl': l, 'nc': nc, 'vr': vr, 'sr': sr
        })

results.sort(key=lambda x: x['pd'], reverse=True)
dc = Counter(r['pd'] for r in results)

print('=' * 60)
print('蜻蜓点水筛选结果汇总')
print('=' * 60)
print('交易日范围: %s ~ %s' % (two_week_start, dates[-1]))
print('扫描股票: %d 只' % len(stock_data))
print('命中结果: %d 只' % len(results))
print()
print('按日期分布:')
for d in sorted(dc.keys(), reverse=True):
    print('  %s: %d 只' % (d, dc[d]))

# 最近3个交易日的股票
recent = [r for r in results if r['pd'] >= dates[-3]]
recent.sort(key=lambda x: x['vr'])
print()
print('最近3个交易日蜻蜓点水股票（按缩量程度排序，共%d只）:' % len(recent))
print('%-12s %-8s %s %8s %8s %8s' % ('代码', '名称', '蜻蜓日', '缩量比', '下影线比', '次日收盘'))
print('-' * 65)
for r in recent:
    print('%-12s %-8s %s %8s %8sx %8.2f' % (
        r['code'], r['name'], r['pd'], r['vr'], r['sr'], r['nc']))
