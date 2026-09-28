"""探测东方财富 datacenter 报表，找到能返回全量A股官方简称的报表。"""
import json
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')


def probe(label, url):
    print(f'--- {label} ---')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode('utf-8', errors='replace'))
        result = payload.get('result') or {}
        pages = result.get('pages')
        data = result.get('data') or []
        print(f'pages={pages}, 本页 {len(data)} 条')
        for row in data[:5]:
            print('   ', row)
        return payload
    except Exception as e:
        print(f'失败: {e}')
        return None
    finally:
        print()


# RPT_F10_BASIC_ORGINFO 基本信息，用 filter 只取A股
probe('RPT_F10_BASIC_ORGINFO 分页',
      'https://datacenter-web.eastmoney.com/api/data/v1/get'
      '?reportName=RPT_F10_BASIC_ORGINFO&pageSize=50&pageNumber=1'
      '&columns=SECURITY_CODE,SECURITY_NAME_ABBR,ORG_NAME')

# 尝试 A 股列表报表
probe('RPTA_WEB_NEWSTOCK_LIST 新股',
      'https://datacenter-web.eastmoney.com/api/data/v1/get'
      '?reportName=RPTA_WEB_NEWSTOCK_LIST&pageSize=5&pageNumber=1'
      '&columns=ALL')

# 尝试沪深京A股清单
probe('RPT_VALUEANALYSIS_DET',
      'https://datacenter-web.eastmoney.com/api/data/v1/get'
      '?reportName=RPT_VALUEANALYSIS_DET&pageSize=5&pageNumber=1'
      '&columns=ALL')
