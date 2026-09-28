"""探测可用的东方财富/新浪接口，获取A股官方简称。"""
import json
import urllib.request

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def try_url(label, url):
    print(f'--- {label} ---')
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        print(f'HTTP OK, {len(raw)} bytes')
        print(raw[:400])
        return raw
    except Exception as e:
        print(f'失败: {e}')
        return None
    finally:
        print()


# 变体1：新浪股票列表
try_url(
    '新浪 stock list',
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
    '?page=1&num=20&sort=symbol&asc=1&node=hs_a',
)

# 变体2：东方财富 clist 精简参数
try_url(
    '东财 clist 精简',
    'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&fs=m:0+t:6&fields=f12,f14',
)

# 变体3：东方财富 82 主机
try_url(
    '东财 push2 82',
    'https://82.push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&fs=m:0+t:6&fields=f12,f14',
)

# 变体4：东方财富单只股票快照
try_url(
    '东财单只快照',
    'https://push2.eastmoney.com/api/qt/stock/get?secid=0.000001&fields=f57,f58',
)

# 变体5：新浪单只
try_url(
    '新浪单只 hq',
    'https://hq.sinajs.cn/list=sz000001',
)
