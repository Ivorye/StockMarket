"""从东方财富 datacenter 获取A股官方简称（SECURITY_NAME_ABBR），更新 stocks 表。"""
import json
import time
import urllib.request

import pymysql

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')

BASE = ('https://datacenter-web.eastmoney.com/api/data/v1/get'
        '?reportName=RPT_F10_BASIC_ORGINFO'
        '&columns=SECURITY_CODE,SECURITY_NAME_ABBR,ORG_NAME'
        '&pageSize={size}&pageNumber={page}&sortColumns=SECURITY_CODE&sortTypes=1')


def fetch_page(page, size=500, retries=3):
    url = BASE.format(page=page, size=size)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode('utf-8', errors='replace'))
            result = payload.get('result') or {}
            return result.get('pages') or 0, result.get('data') or []
        except Exception as e:
            print(f'  第 {page} 页第 {attempt + 1} 次失败: {e}')
            time.sleep(2)
    return None, []


def fetch_all():
    """返回 {6位代码: 官方简称}，只保留带后缀判断的A股代码。"""
    pages, first = fetch_page(1)
    if pages is None:
        raise SystemExit('首页抓取失败')
    print(f'共 {pages} 页')
    mapping = {}
    for row in first:
        code = str(row.get('SECURITY_CODE') or '').strip()
        name = str(row.get('SECURITY_NAME_ABBR') or '').strip()
        if code and name:
            mapping[code] = name
    for page in range(2, pages + 1):
        _, data = fetch_page(page)
        for row in data:
            code = str(row.get('SECURITY_CODE') or '').strip()
            name = str(row.get('SECURITY_NAME_ABBR') or '').strip()
            if code and name:
                mapping[code] = name
        if page % 50 == 0:
            print(f'  已抓取 {page}/{pages} 页，累计 {len(mapping)} 条')
        time.sleep(0.15)
    return mapping


def main():
    names = fetch_all()
    print(f'\n共获取官方简称 {len(names)} 条')

    db = pymysql.connect(host='localhost', user='root', password='P@ssw0rd',
                         database='stockshare', connect_timeout=10,
                         read_timeout=60, write_timeout=60)
    cursor = db.cursor()
    cursor.execute('SELECT st_code FROM stocks')
    db_codes = [row[0] for row in cursor.fetchall()]
    print(f'stocks 表中共 {len(db_codes)} 只股票')

    updates, missing = [], []
    for st_code in db_codes:
        symbol = st_code.split('.')[0]
        official = names.get(symbol)
        if official:
            updates.append((official, st_code))
        else:
            missing.append(st_code)

    cursor.executemany('UPDATE stocks SET name=%s WHERE st_code=%s', updates)
    db.commit()
    print(f'已更新 {len(updates)} 条官方简称')
    if missing:
        print(f'未匹配到 {len(missing)} 条: {missing[:30]}')

    cursor.execute("SELECT st_code, name, fullname FROM stocks LIMIT 10")
    print('\n更新后验证:')
    for r in cursor.fetchall():
        print(f'  {r[0]}  简称={r[1]}  全称={r[2]}')
    cursor.execute("SELECT COUNT(*) FROM stocks WHERE name IS NOT NULL AND name != ''")
    print(f'\n有简称的记录总数: {cursor.fetchone()[0]} / {len(db_codes)}')
    db.close()


if __name__ == '__main__':
    main()
