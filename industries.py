# -*- coding: utf-8 -*-
"""行业板块数据：从东方财富 datacenter 批量抓取并缓存到 stocks.industry 列。

使用 RPT_F10_BASIC_ORGINFO 报表（免 token），按 SECURITY_CODE 批量过滤：
    BOARD_NAME_LEVEL = "一级-二级-三级"（如 电子-半导体-半导体材料）
取二级板块作为“行业板块”（如 半导体、银行、白酒），更贴近常用口径。
当 BOARD_NAME_LEVEL 缺失时回退到 EM2016 的对应层级。
行业写入 stocks.industry，按需抓取、查过一次即缓存。
"""
import re
import time

import requests

import db_utils

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
_DC = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
_REPORT = 'RPT_F10_BASIC_ORGINFO'
_COLUMNS = 'SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME_LEVEL,EM2016'
_BATCH = 80
_TIMEOUT = 20
_ROMAN_RE = re.compile(r'(?:Ⅲ|Ⅱ|Ⅰ|IV|III|II|I)$')


def ensure_industry_column():
    """给 stocks 表补上 industry(行业) 列，已存在则跳过。"""
    db = db_utils.connect_pymysql()
    try:
        cursor = db.cursor()
        try:
            cursor.execute("ALTER TABLE stocks ADD COLUMN industry VARCHAR(50) DEFAULT ''")
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _strip_roman(text):
    return _ROMAN_RE.sub('', text or '').strip()


def _parse_board(board_level, em2016):
    """从 "一级-二级-三级" 中取二级板块，去掉罗马数字后缀。"""
    for raw in (board_level, em2016):
        if not raw:
            continue
        parts = [p.strip() for p in str(raw).split('-') if p.strip()]
        if not parts:
            continue
        seg = parts[1] if len(parts) >= 2 else parts[0]
        seg = _strip_roman(seg)
        if seg:
            return seg
    return ''


def _fetch_batch(codes, retries=3):
    """批量抓取一批 6 位代码的行业，返回 {symbol: industry}。"""
    codes = [c for c in codes if c]
    if not codes:
        return {}
    flt = '(SECURITY_CODE in (' + ','.join('"%s"' % c for c in codes) + '))'
    params = {
        'reportName': _REPORT,
        'columns': _COLUMNS,
        'pageSize': max(100, len(codes)),
        'pageNumber': 1,
        'filter': flt,
    }
    for attempt in range(retries):
        try:
            resp = requests.get(_DC, params=params,
                                headers={'User-Agent': _UA, 'Referer': 'https://data.eastmoney.com/'},
                                timeout=_TIMEOUT)
            resp.raise_for_status()
            rows = ((resp.json() or {}).get('result') or {}).get('data') or []
            mapping = {}
            for row in rows:
                code = str(row.get('SECURITY_CODE') or '').strip()
                if not code:
                    continue
                industry = _parse_board(row.get('BOARD_NAME_LEVEL'), row.get('EM2016'))
                if industry:
                    mapping[code] = industry
            return mapping
        except Exception as exc:
            print(f'行业抓取失败(第{attempt + 1}次) {codes[:3]}...: {exc}')
            time.sleep(1.5)
    return {}


def fetch_industries(codes):
    """按 6 位代码批量抓取行业（自动分批），返回 {symbol: industry}。"""
    result = {}
    codes = list(dict.fromkeys(c for c in codes if c))
    for i in range(0, len(codes), _BATCH):
        result.update(_fetch_batch(codes[i:i + _BATCH]))
        if i + _BATCH < len(codes):
            time.sleep(0.05)
    return result


def _persist(mapping):
    if not mapping:
        return 0
    db = db_utils.connect_pymysql()
    try:
        cursor = db.cursor()
        cursor.executemany(
            "UPDATE stocks SET industry=%s WHERE symbol=%s",
            [(industry, symbol) for symbol, industry in mapping.items()],
        )
        db.commit()
        return len(mapping)
    finally:
        db.close()


def industry_map(st_codes):
    """按股票代码批量读取行业，返回 {st_code: industry}。"""
    codes = [c for c in st_codes if c]
    result = {}
    if not codes:
        return result
    db = db_utils.connect_pymysql()
    try:
        cursor = db.cursor()
        for i in range(0, len(codes), 1000):
            chunk = codes[i:i + 1000]
            placeholders = ','.join(['%s'] * len(chunk))
            cursor.execute(
                "SELECT st_code, COALESCE(industry,'') FROM stocks "
                "WHERE st_code IN (" + placeholders + ")",
                tuple(chunk),
            )
            for st_code, industry in cursor.fetchall():
                result[st_code] = industry
    finally:
        db.close()
    return result


def ensure_industries(st_codes):
    """读取行业；缺失的按需抓取并落库，返回 {st_code: industry}。"""
    codes = [c for c in st_codes if c]
    result = industry_map(codes)
    missing = [c for c in codes if not result.get(c)]
    if not missing:
        return result
    symbols = list(dict.fromkeys(c.split('.')[0] for c in missing))
    fetched = fetch_industries(symbols)
    if not fetched:
        return result
    _persist(fetched)
    for code in missing:
        industry = fetched.get(code.split('.')[0])
        if industry:
            result[code] = industry
    return result


def refresh_industries(codes=None):
    """抓取行业并写回 stocks.industry。codes 为 6 位代码列表，缺省为全库股票。"""
    ensure_industry_column()
    if codes is None:
        db = db_utils.connect_pymysql()
        try:
            cursor = db.cursor()
            cursor.execute("SELECT symbol, st_code FROM stocks")
            codes = [row[0] for row in cursor.fetchall()]
        finally:
            db.close()
    mapping = fetch_industries(codes)
    return _persist(mapping)


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    if len(sys.argv) > 1 and sys.argv[1] == 'all':
        count = refresh_industries()
        print(f'全库行业更新完成：{count} 条')
    else:
        sample = ['301313.SZ', '688146.SH', '600519.SH', '000001.SZ']
        print('样例行业：', ensure_industries(sample))

    db = db_utils.connect_pymysql()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM stocks WHERE COALESCE(industry,'')<>''")
    print(f'库中有行业的股票数：{cursor.fetchone()[0]}')
    cursor.execute("SELECT industry, COUNT(*) FROM stocks WHERE COALESCE(industry,'')<>'' "
                   "GROUP BY industry ORDER BY COUNT(*) DESC LIMIT 15")
    for industry, n in cursor.fetchall():
        print(f'  {industry}: {n}')
    db.close()
