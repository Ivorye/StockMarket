import pymysql

db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd', database='stockshare')
cursor = db.cursor()

cursor.execute('SELECT symbol, st_code FROM stocks')
stocks = cursor.fetchall()

cursor.execute('SELECT MAX(trade_date) FROM `gp000001`')
latest_date = cursor.fetchone()[0]

cursor.execute('SELECT DISTINCT trade_date FROM `gp000001` ORDER BY trade_date DESC LIMIT 2')
dates = cursor.fetchall()
today = dates[0][0]
prev_day = dates[1][0]

# ---- 策略1: 放量涨幅 ----
s1 = {}
for symbol, st_code in stocks:
    table = '`gp%s`' % symbol
    try:
        cursor.execute('SELECT trade_date, openp, high, low, closep, pct_chg, vol '
                       'FROM %s WHERE trade_date IN (%%s, %%s) ORDER BY trade_date' % table, (prev_day, today))
        rows = cursor.fetchall()
        if len(rows) == 2:
            prev_data, today_data = rows
            pct_chg = today_data[5]
            vol_today = today_data[6]
            vol_prev = prev_data[6]
            if vol_prev > 0 and vol_today >= vol_prev * 3 and pct_chg > 6 and not symbol.startswith('688'):
                s1[symbol] = {
                    'st_code': st_code, 'pct_chg': pct_chg,
                    'vol_ratio': round(vol_today / vol_prev, 2),
                    'vol_today': vol_today, 'vol_prev': vol_prev
                }
    except:
        pass

# ---- 策略2: 向上跳空缺口 ----
s2 = {}
for symbol, st_code in stocks:
    if symbol.startswith('688'):
        continue
    table = '`gp%s`' % symbol
    try:
        cursor.execute('SELECT trade_date, openp, high, low, closep, pct_chg, vol '
                       'FROM %s WHERE trade_date IN (%%s, %%s) ORDER BY trade_date' % table, (prev_day, today))
        rows = cursor.fetchall()
        if len(rows) == 2:
            prev_data, today_data = rows
            prev_high = prev_data[2]
            prev_close = prev_data[4]
            prev_vol = prev_data[6]
            today_low = today_data[3]
            today_close = today_data[4]
            today_pct_chg = today_data[5]
            today_vol = today_data[6]
            if today_low > prev_high and today_close > prev_close:
                vol_ratio = round(today_vol / prev_vol, 2) if prev_vol > 0 else 0
                s2[symbol] = {
                    'st_code': st_code, 'pct_chg': today_pct_chg,
                    'vol_ratio': vol_ratio, 'gap': round(today_low - prev_high, 2),
                    'vol_today': today_vol, 'vol_prev': prev_vol
                }
    except:
        pass

db.close()

# ---- 分析 ----
set1 = set(s1.keys())
set2 = set(s2.keys())
both = set1 & set2
only1 = set1 - set2
only2 = set2 - set1

print(f'筛选日期: {today} vs {prev_day}')
print(f'{"="*70}')
print(f'放量涨幅策略: {len(s1)} 只')
print(f'跳空缺口策略: {len(s2)} 只')
print(f'重叠: {len(both)} 只')
print(f'仅放量涨幅: {len(only1)} 只')
print(f'仅跳空缺口: {len(only2)} 只')
print(f'重叠率(相对放量涨幅): {len(both)/len(s1)*100:.1f}%')
print(f'重叠率(相对跳空缺口): {len(both)/len(s2)*100:.1f}%')

# 按涨幅排序输出
print(f'\n{"="*70}')
print(f'【重叠股票】两个策略都命中 ({len(both)} 只)')
print(f'{"="*70}')
print(f'{"股票":<12} {"涨幅%":>7} {"量比S1":>8} {"量比S2":>8} {"缺口":>6}')
print(f'{"-"*50}')
for sym in sorted(both, key=lambda x: s1[x]['pct_chg'], reverse=True):
    d1, d2 = s1[sym], s2[sym]
    print(f'{d1["st_code"]:<12} {d1["pct_chg"]:>7.2f} {d1["vol_ratio"]:>8.2f} {d2["vol_ratio"]:>8.2f} {d2["gap"]:>6.2f}')

print(f'\n{"="*70}')
print(f'【仅放量涨幅】无跳空缺口 ({len(only1)} 只)')
print(f'{"="*70}')
print(f'{"股票":<12} {"涨幅%":>7} {"量比":>8}')
print(f'{"-"*35}')
for sym in sorted(only1, key=lambda x: s1[x]['pct_chg'], reverse=True):
    d = s1[sym]
    print(f'{d["st_code"]:<12} {d["pct_chg"]:>7.2f} {d["vol_ratio"]:>8.2f}')

print(f'\n{"="*70}')
print(f'【仅跳空缺口】涨幅不够或量比不足 ({len(only2)} 只)')
print(f'{"="*70}')
print(f'{"股票":<12} {"涨幅%":>7} {"量比":>8} {"缺口":>6}')
print(f'{"-"*40}')
for sym in sorted(only2, key=lambda x: s2[x]['pct_chg'], reverse=True):
    d = s2[sym]
    print(f'{d["st_code"]:<12} {d["pct_chg"]:>7.2f} {d["vol_ratio"]:>8.2f} {d["gap"]:>6.2f}')

# ---- 数值统计 ----
import statistics

def stat(label, vals):
    if not vals:
        return f'{label}: 无数据'
    return (f'{label} ({len(vals)}只): '
            f'均值={statistics.mean(vals):.2f}  中位={statistics.median(vals):.2f}  '
            f'最大={max(vals):.2f}  最小={min(vals):.2f}')

print(f'\n{"="*70}')
print('数值统计')
print(f'{"="*70}')

# 重叠组
if both:
    vr_both_s1 = [s1[s]['vol_ratio'] for s in both]
    vr_both_s2 = [s2[s]['vol_ratio'] for s in both]
    pct_both = [s1[s]['pct_chg'] for s in both]
    print(stat('重叠组-涨幅', pct_both))
    print(stat('重叠组-量比(放量涨幅)', vr_both_s1))
    print(stat('重叠组-量比(跳空缺口)', vr_both_s2))

# 仅放量涨幅
if only1:
    vr1 = [s1[s]['vol_ratio'] for s in only1]
    pct1 = [s1[s]['pct_chg'] for s in only1]
    print(stat('仅放量涨幅-涨幅', pct1))
    print(stat('仅放量涨幅-量比', vr1))

# 仅跳空缺口
if only2:
    vr2 = [s2[s]['vol_ratio'] for s in only2]
    pct2 = [s2[s]['pct_chg'] for s in only2]
    print(stat('仅跳空缺口-涨幅', pct2))
    print(stat('仅跳空缺口-量比', vr2))

# 规律总结
print(f'\n{"="*70}')
print('规律分析')
print(f'{"="*70}')

# 重叠组涨幅 vs 仅跳空缺口涨幅
if both and only2:
    avg_both = statistics.mean([s1[s]['pct_chg'] for s in both])
    avg_only2 = statistics.mean([s2[s]['pct_chg'] for s in only2])
    print(f'重叠组平均涨幅: {avg_both:.2f}%  |  仅跳空缺口平均涨幅: {avg_only2:.2f}%')
    print(f'  -> 重叠组涨幅明显更高，说明"跳空+放量+大涨"是更强信号')

if both and only1:
    avg_both_vr = statistics.mean([s1[s]['vol_ratio'] for s in both])
    avg_only1_vr = statistics.mean([s1[s]['vol_ratio'] for s in only1])
    print(f'重叠组平均量比: {avg_both_vr:.2f}  |  仅放量涨幅平均量比: {avg_only1_vr:.2f}')
    print(f'  -> 对比两组量比，看是否有量比差异')

# 跳空缺口中有多少是小涨幅的
if only2:
    low_pct = [s for s in only2 if s2[s]['pct_chg'] < 6]
    print(f'仅跳空缺口中涨幅<6%的: {len(low_pct)}/{len(only2)}')
    print(f'  -> 这些股票有跳空缺口但涨幅不够放量涨幅策略的阈值(6%)')

# 跳空缺口中有多少是缩量的
if only2:
    low_vol = [s for s in only2 if s2[s]['vol_ratio'] < 3]
    print(f'仅跳空缺口中量比<3的: {len(low_vol)}/{len(only2)}')
    print(f'  -> 这些股票有跳空缺口但放量不够放量涨幅策略的阈值(3倍)')
