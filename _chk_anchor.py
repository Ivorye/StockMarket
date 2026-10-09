import io, sys, importlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import main as M
import stockPolicy as sp
importlib.reload(M)

ANCHORS = ['', '20260914', '20260821']

print('=' * 78)
print('小旗杆: 基准日 vs 扫描结果的旗杆日')
print('=' * 78)
for a in ANCHORS:
    d = M._load_small_pole(anchor=a)
    rec = d['records']
    poles = [r.get('trade_date') for r in rec]
    flag = 'OK' if (not a or (poles and max(poles) <= a)) else '!! 越界'
    print('anchor=%-10s count=%-4d 区间 %s ~ %s  旗杆日 max=%s  %s'
          % (a or '(最新)', d['count'], d['start_date'], d['signal_date'],
             max(poles) if poles else '-', flag))
    if a:
        bad = [p for p in poles if p > a]
        if bad:
            print('    越界样本:', bad[:5])

print()
print('=' * 78)
print('上升旗形: 基准日 vs 扫描结果的信号日')
print('=' * 78)
for a in ANCHORS:
    d = M._load_bull_flag(anchor=a, trading_days=10)
    rec = d['records']
    sig = [r.get('trade_date') for r in rec]
    flag = 'OK' if (not a or (sig and max(sig) <= a)) else '!! 越界'
    print('anchor=%-10s count=%-4d 区间 %s ~ %s  信号日 max=%s  %s'
          % (a or '(最新)', d['count'], d['start_date'], d['signal_date'],
             max(sig) if sig else '-', flag))

print()
print('=' * 78)
print('不同基准日应返回不同结果（缓存按 anchor 分离）')
print('=' * 78)
c1 = M._load_small_pole(anchor='20260914')['count']
c2 = M._load_small_pole(anchor='20260821')['count']
c3 = M._load_small_pole()['count']
print('小旗杆  0914=%d  0821=%d  最新=%d  ->  %s'
      % (c1, c2, c3, 'OK' if len({c1, c2, c3}) > 1 else '!! 相同'))
b1 = M._load_bull_flag(anchor='20260914')['count']
b3 = M._load_bull_flag()['count']
print('旗形    0914=%d  最新=%d -> %s' % (b1, b3, 'OK' if b1 != b3 else '(可能相同)'))
