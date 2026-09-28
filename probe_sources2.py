"""探测东方财富接口的多种请求形式，绕过 502。"""
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')


def try_url(label, url, headers=None):
    h = {'User-Agent': UA, 'Accept': '*/*'}
    if headers:
        h.update(headers)
    print(f'--- {label} ---')
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        print(f'HTTP OK, {len(raw)} bytes')
        print(raw[:300])
    except Exception as e:
        print(f'失败: {e}')
    finally:
        print()


base = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&fields=f12,f14'

# 加 Referer
try_url('带Referer', base + '&fs=m:0+t:6',
        {'Referer': 'https://quote.eastmoney.com/'})

# JSONP 回调
try_url('JSONP', base + '&fs=m:0+t:6&cb=jQuery123',
        {'Referer': 'https://quote.eastmoney.com/'})

# http 而非 https
try_url('HTTP明文', base.replace('https://', 'http://') + '&fs=m:0+t:6',
        {'Referer': 'http://quote.eastmoney.com/'})

# 去掉 fs 参数
try_url('无fs参数', base, {'Referer': 'https://quote.eastmoney.com/'})

# 备用域名 push2his / 其他
try_url('datacenter', 
        'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_F10_BASIC_ORGINFO&pageSize=10&pageNumber=1&columns=SECURITY_CODE,SECURITY_NAME_ABBR')
