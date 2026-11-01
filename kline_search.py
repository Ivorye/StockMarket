# -*- coding: utf-8 -*-
"""K 线形态查询：从上传的 K 线截图提取走势，在全市场股票中查找形态相似的历史区间。

截图识别假定与本系统一致的配色：阳线（涨）红色、阴线（跌）绿色。
成交量柱颜色较浅，按颜色阈值会被排除。

形态比较：把窗口内 N 根 K 线的 开/高/低/收 展开成 4N 维向量，去均值并单位化后，
与截图模板向量求内积即为相关系数。相关系数对整体价位和涨跌幅幅度不敏感，只看形状。

全市场行情读入耗时较长（约数分钟），因此进程启动时后台预加载到内存，
之后按 st_daily 的最新交易日自动刷新，查询时只做矩阵运算。
"""
import base64
import io
import logging
import threading
import time
import uuid

import numpy as np
import pymysql
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image, ImageDraw

logger = logging.getLogger('kline_search')

MIN_CANDLES = 5
MAX_CANDLES = 300
MAX_PER_STOCK = 3
MAX_RESULTS = 300
_MAX_IMAGES = 20
_MAX_JOBS = 20
_IMAGES = {}
_JOBS = {}
_LOCK = threading.Lock()
_BUILD_LOCK = threading.Lock()
_DATA = {'key': None, 'series': {}, 'names': {}}


def _color_masks(a, sat_min=0.45, diff_min=45):
    """返回 (红, 绿) 像素掩码。

    用「通道差值 + 饱和度」而不是固定 RGB 区间：能兼容常见的鲜红/深红/翠绿等配色，
    同时把半透明的成交量柱（饱和度低）和灰色网格排除掉。
    """
    r = a[..., 0].astype(np.int32)
    g = a[..., 1].astype(np.int32)
    b = a[..., 2].astype(np.int32)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0.0)
    red = (r - np.maximum(g, b) > diff_min) & (r > 100) & (sat > sat_min)
    green = (g - np.maximum(r, b) > diff_min) & (g > 80) & (sat > sat_min)
    return red, green


def _cluster_groups(groups):
    """把列组按横向大间隔分成若干簇。

    整页截图里除了图表，还有红色的涨跌文字、标签、按钮等零散彩色像素。
    图表区的蜡烛排列紧密，零散元素之间间隔大，因此取「列组最多」的那一簇即可。
    """
    if not groups:
        return []
    widths = [len(g) for g in groups]
    median_w = float(np.median(widths)) or 1.0
    gap_limit = max(8.0, 3.0 * median_w)
    clusters = [[groups[0]]]
    for prev, grp in zip(groups, groups[1:]):
        gap = float(int(grp[0]) - int(prev[-1]) - 1)
        if gap > gap_limit:
            clusters.append([grp])
        else:
            clusters[-1].append(grp)
    return clusters


def _runs(rows):
    """把行号数组切成连续段。"""
    if rows.size == 0:
        return []
    return np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1)


def _build_candles(red, green, min_run=3, min_width=2):
    """由红/绿掩码构建每根 K 线的像素坐标。"""
    cols = np.flatnonzero((red | green).sum(axis=0) > 0)
    if cols.size == 0:
        return []
    groups = np.split(cols, np.flatnonzero(np.diff(cols) > 1) + 1)
    groups = [g for g in groups if len(g) >= min_width]
    if not groups:
        return []
    # 整页截图可能混入页面上的红色文字/标签，取列组最密集的一簇作为图表区
    clusters = _cluster_groups(groups)
    if len(clusters) > 1:
        groups = max(clusters, key=len)
    # 截图较小时相邻蜡烛的实体可能横向粘连，按中位宽度把过宽的列组拆开
    widths = [len(g) for g in groups]
    median_w = float(np.median(widths)) if widths else 0.0
    split_groups = []
    for grp in groups:
        if median_w >= 3 and len(grp) > 1.8 * median_w:
            parts = max(2, min(int(round(len(grp) / median_w)), 8))
            split_groups.extend(np.array_split(grp, parts))
        else:
            split_groups.append(grp)
    candles = []
    for grp in split_groups:
        x0, x1 = int(grp[0]), int(grp[-1]) + 1
        sub_red = red[:, x0:x1]
        sub_green = green[:, x0:x1]
        row_count = (sub_red | sub_green).sum(axis=1)
        rows = np.flatnonzero(row_count > 0)
        if rows.size == 0:
            continue
        # 一列像素可能横跨「价格区」和「成交量区」。价格区永远在上方，
        # 因此取最上方的连续段，避免把下方的成交量柱算进最高/最低价。
        runs = [r for r in _runs(rows) if r.size >= min_run]
        if not runs:
            continue
        band = runs[0]
        top_y, bottom_y = int(band[0]), int(band[-1])
        local = row_count[top_y:bottom_y + 1]
        body = np.flatnonzero(local >= max(1.0, 0.5 * local.max())) + top_y
        if body.size == 0:
            continue
        body_top, body_bottom = int(body[0]), int(body[-1])
        band_red = int(sub_red[top_y:bottom_y + 1].sum())
        band_green = int(sub_green[top_y:bottom_y + 1].sum())
        if band_red >= band_green:
            open_y, close_y = body_bottom, body_top
        else:
            open_y, close_y = body_top, body_bottom
        candles.append((top_y, bottom_y, open_y, close_y))
    return candles


def extract_pattern(image_bytes):
    """从截图中提取 K 线，返回形状 (N,4) 的数组，列为 [开, 高, 低, 收]（未归一化，仅用于形状比较）。"""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    except Exception as exc:
        raise ValueError('无法识别图片格式，请上传 PNG/JPG 图片') from exc
    array = np.asarray(img)
    height_px, width_px = array.shape[0], array.shape[1]

    # 先按严格参数识别；失败再用放宽参数重试（兼容压缩、偏色、小尺寸截图）
    attempts = [
        dict(sat_min=0.45, diff_min=45, min_run=3, min_width=2),
        dict(sat_min=0.25, diff_min=22, min_run=2, min_width=1),
    ]
    best_candles = []
    last_red = last_green = None
    for params in attempts:
        red, green = _color_masks(array, params['sat_min'], params['diff_min'])
        last_red, last_green = red, green
        candles = _build_candles(red, green, params['min_run'], params['min_width'])
        if MIN_CANDLES <= len(candles) <= MAX_CANDLES:
            best_candles = candles
            break
        if len(candles) > len(best_candles):
            best_candles = candles
    candles = best_candles

    if not candles:
        red_px = int(last_red.sum()) if last_red is not None else 0
        green_px = int(last_green.sum()) if last_green is not None else 0
        raise ValueError(
            f'未找到红绿K线（红像素 {red_px}，绿像素 {green_px}，图片 {width_px}×{height_px}）。'
            f'请截图包含红涨绿跌的K线蜡烛')
    if not (MIN_CANDLES <= len(candles) <= MAX_CANDLES):
        raise ValueError(
            f'识别到 {len(candles)} 根K线，需在 {MIN_CANDLES}~{MAX_CANDLES} 根之间'
            f'（图片 {width_px}×{height_px}）。请只截取图表区域，避免包含大量文字或图表过小')
    arr = np.array(candles, dtype=float)
    # 图像 y 轴向下，价格 = -y
    return np.stack([-arr[:, 2], -arr[:, 0], -arr[:, 1], -arr[:, 3]], axis=1)


def render_pattern_preview(pattern):
    """把识别出的形态画成小图，返回 data URL，供用户核对识别是否正确。"""
    n = len(pattern)
    width = int(max(320, min(900, n * 13)))
    height = 170
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    hi = float(pattern[:, 1].max())
    lo = float(pattern[:, 2].min())
    span = hi - lo or 1.0
    pad = 10
    step = (width - 2 * pad) / max(1, n)
    body_w = max(2.0, step * 0.6)

    def y_of(price):
        return pad + (hi - price) / span * (height - 2 * pad)

    for i in range(n):
        o, h, l, c = (float(pattern[i, 0]), float(pattern[i, 1]),
                      float(pattern[i, 2]), float(pattern[i, 3]))
        x = pad + step * (i + 0.5)
        color = (207, 19, 34) if c >= o else (56, 158, 13)
        draw.line([(x, y_of(h)), (x, y_of(l))], fill=color, width=1)
        y1, y2 = y_of(max(o, c)), y_of(min(o, c))
        draw.rectangle([x - body_w / 2, y1, x + body_w / 2, max(y1 + 1, y2)], fill=color)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _normalize_candles(windows):
    """按窗口自身的最高/最低价把 OHLC 归一化到 [0,1]。

    windows: (M, N, 4)
    注：截图的纵轴是像素坐标，与真实价格只差一个线性变换，因此振幅/涨跌幅无法还原，
    只能比较归一化后的形状。
    """
    lo = windows[:, :, 2].min(axis=1, keepdims=True)   # (M,1)
    hi = windows[:, :, 1].max(axis=1, keepdims=True)   # (M,1)
    rng = hi - lo
    if np.any(rng <= 0):
        safe = np.where(rng <= 0, 1.0, rng)
    else:
        safe = rng
    return (windows - lo[:, :, None]) / safe[:, :, None]


def _pattern_norm(pattern):
    """模板归一化，并校验形态有效。"""
    normalized = _normalize_candles(pattern[None, :, :].astype(np.float64))
    if float(normalized.max() - normalized.min()) < 1e-6:
        raise ValueError('K线形态无变化，无法比较，请换一张截图')
    return normalized[0].astype(np.float32)


def store_pattern(image_bytes):
    pattern = extract_pattern(image_bytes)
    preview = render_pattern_preview(pattern)
    image_id = uuid.uuid4().hex
    with _LOCK:
        _IMAGES[image_id] = (pattern, _pattern_norm(pattern))

        while len(_IMAGES) > _MAX_IMAGES:
            _IMAGES.pop(next(iter(_IMAGES)))
    return image_id, len(pattern), preview


def _match_stock(arr, pat_norm, n, threshold):
    """arr: (L,4) 列为 开/高/低/收。

    相似度 = 1 - RMSE，其中两边都按各自窗口的最高/最低价归一化到 [0,1]。
    这接近「肉眼看形状」：只看轮廓与节奏，不看绝对价位。
    """
    if arr.shape[0] < n:
        return []
    windows = np.stack([sliding_window_view(arr[:, i], n) for i in range(4)], axis=2).astype(np.float32)
    normalized = _normalize_candles(windows.astype(np.float64)).astype(np.float32)
    diff = normalized - pat_norm[None, :, :]
    score = 1.0 - np.sqrt((diff * diff).mean(axis=(1, 2)))
    gap = max(1, n // 2)
    picked = []
    for i in np.argsort(-score):
        if score[i] < threshold:
            break
        i = int(i)
        if all(abs(i - j) >= gap for j, _ in picked):
            picked.append((i, float(score[i])))
            if len(picked) >= MAX_PER_STOCK:
                break
    return picked


def _connect(read_timeout=600):
    return pymysql.connect(
        host='localhost', user='root', password='P@ssw0rd', database='stockshare',
        connect_timeout=15, read_timeout=read_timeout, write_timeout=60,
    )


def _latest_key(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(trade_date) FROM st_daily")
    row = cursor.fetchone()
    return row[0] if row else None


def _load_names(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT st_code, COALESCE(NULLIF(name,''), fullname, '') FROM stocks")
    return {code: name for code, name in cursor.fetchall()}


def _iter_stock_series(conn):
    """流式按股票输出 [(日期, 开, 高, 低, 收), ...]。"""
    cursor = conn.cursor(pymysql.cursors.SSCursor)
    cursor.execute(
        "SELECT ts_code, trade_date, openp, high, low, closep FROM st_daily "
        "ORDER BY ts_code, trade_date")
    cur_code = None
    buf = []
    for code, d, o, h, lo, c in cursor:
        if code != cur_code:
            if buf:
                yield cur_code, buf
            cur_code = code
            buf = []
        if o and h and lo and c and o > 0 and h > 0 and lo > 0 and c > 0:
            buf.append((d, float(o), float(h), float(lo), float(c)))
    if buf:
        yield cur_code, buf
    cursor.close()


def ensure_series():
    """确保内存中的全市场行情与数据库最新交易日一致；必要时重新加载。返回数据版本键。"""
    with _BUILD_LOCK:
        conn = _connect()
        try:
            key = _latest_key(conn)
        finally:
            conn.close()
        if _DATA['key'] == key and _DATA['series']:
            return key
        started = time.time()
        conn = _connect()
        try:
            names = _load_names(conn)
            series = {}
            for code, rows in _iter_stock_series(conn):
                if len(rows) < 2:
                    continue
                dates = np.array([int(r[0]) for r in rows], dtype=np.int32)
                arr = np.array([r[1:] for r in rows], dtype=np.float32)
                series[code] = (dates, arr)
        finally:
            conn.close()
        _DATA.update(key=key, series=series, names=names)
        logger.info('K线形态行情已加载：%s 只股票，耗时 %.0fs，最新交易日 %s',
                    len(series), time.time() - started, key)
        return key


def warm_up_async(delay=25):
    """启动后台预加载全市场行情。

    延迟 delay 秒再开始：避免与首页/接口的首批查询抢数据库 I/O。
    """
    def _run():
        if delay:
            time.sleep(delay)
        try:
            ensure_series()
        except Exception:
            logger.exception('K线形态行情预加载失败')
    threading.Thread(target=_run, daemon=True).start()


def _eastmoney_url(st_code):
    parts = st_code.split('.')
    if len(parts) == 2:
        return f'https://quote.eastmoney.com/{parts[1].lower()}{parts[0]}.html'
    return '#'


def _run_job(job_id, pat_norm, n, threshold):
    job = _JOBS[job_id]
    try:
        import stockPolicy as sp
        import industries as ind
        job['stage'] = 'loading'
        ensure_series()
        series = _DATA['series']
        names = _DATA['names']
        job.update(stage='scanning', total=len(series))

        matched = []
        for code, (dates, arr) in series.items():
            job['processed'] += 1
            name = names.get(code, '')
            if sp._is_delisted(name):
                continue
            picked = _match_stock(arr, pat_norm, n, threshold)
            if not picked:
                continue
            items = sorted(
                [{'start_date': str(int(dates[i])), 'end_date': str(int(dates[i + n - 1])),
                  'similarity': round(s * 100, 1)} for i, s in picked],
                key=lambda m: m['start_date'])
            matched.append({
                'st_code': code,
                'name': name,
                'eastmoney_url': _eastmoney_url(code),
                'best_similarity': round(max(s for _, s in picked) * 100, 1),
                'matches': items,
            })

        matched.sort(key=lambda x: x['best_similarity'], reverse=True)
        results = matched[:MAX_RESULTS]
        try:
            industry = ind.ensure_industries([r['st_code'] for r in results])
            for r in results:
                r['industry'] = industry.get(r['st_code'], '') or ''
        except Exception:
            logger.exception('行业补充失败')
        job.update(status='done', results=results, matched_total=len(matched), finished=time.time())
    except Exception as exc:
        logger.exception('K线形态查询失败')
        job.update(status='error', error=str(exc), finished=time.time())


def start_job(image_id, threshold):
    with _LOCK:
        entry = _IMAGES.get(image_id)
    if entry is None:
        raise KeyError('图片已失效，请重新上传')
    pattern, pat_norm = entry
    job_id = uuid.uuid4().hex
    with _LOCK:
        _JOBS[job_id] = {
            'status': 'running', 'stage': 'queued', 'processed': 0, 'total': 0,
            'results': [], 'matched_total': 0, 'error': '',
            'candles': len(pattern), 'threshold': round(threshold * 100, 1),
            'started': time.time(), 'finished': None,
        }
        while len(_JOBS) > _MAX_JOBS:
            _JOBS.pop(next(iter(_JOBS)))
    threading.Thread(target=_run_job,
                     args=(job_id, pat_norm, len(pattern), threshold), daemon=True).start()
    return job_id


def get_job(job_id):
    with _LOCK:
        return _JOBS.get(job_id)


def decode_data_url(raw):
    if raw.startswith('data:') and ',' in raw:
        raw = raw.split(',', 1)[1]
    return base64.b64decode(raw)
