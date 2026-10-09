
function switchTab(event, name) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('panel-' + name).classList.add('active');
}
let smoothSort = { column: 3, ascending: false };
function sortSmooth(column) {
    const body = document.querySelector('#smooth-table tbody');
    if (!body) return;
    smoothSort.ascending = smoothSort.column === column ? !smoothSort.ascending : false;
    smoothSort.column = column;
    const rows = Array.from(body.rows);
    rows.sort((a, b) => {
        const av = Number(a.cells[column].dataset.value);
        const bv = Number(b.cells[column].dataset.value);
        return smoothSort.ascending ? av - bv : bv - av;
    });
    rows.forEach((row, index) => { row.cells[0].textContent = index + 1; body.appendChild(row); });
}
let flagSort = { column: 3, ascending: false };
function sortFlag(column) {
    const body = document.querySelector('#bullflag-table tbody');
    if (!body) return;
    flagSort.ascending = flagSort.column === column ? !flagSort.ascending : false;
    flagSort.column = column;
    const rows = Array.from(body.rows);
    rows.sort((a, b) => {
        const av = Number(a.cells[column].dataset.value);
        const bv = Number(b.cells[column].dataset.value);
        return flagSort.ascending ? av - bv : bv - av;
    });
    rows.forEach((row, index) => { row.cells[0].textContent = index + 1; body.appendChild(row); });
}
let poleSort = { column: 3, ascending: false };
function sortPole(column) {
    const body = document.querySelector('#smallpole-table tbody');
    if (!body) return;
    poleSort.ascending = poleSort.column === column ? !poleSort.ascending : (column === 3);
    poleSort.column = column;
    const rows = Array.from(body.rows);
    rows.sort((a, b) => {
        const av = Number(a.cells[column].dataset.value);
        const bv = Number(b.cells[column].dataset.value);
        return poleSort.ascending ? av - bv : bv - av;
    });
    rows.forEach((row, index) => { row.cells[0].textContent = index + 1; body.appendChild(row); });
}
const overlay = document.getElementById('chart-overlay');
const statusEl = document.getElementById('chart-status');
const canvas = document.getElementById('kline-canvas');
const preview = document.getElementById('kline-preview');
const previewCanvas = document.getElementById('kline-preview-canvas');
const previewStatus = document.getElementById('preview-status');
let lastChartButton = null;
let currentChartItems = [];
let currentChartCode = '';
let currentChartDays = 120;
let currentChartLatest = false;
let currentChartEndDate = '';
let previewTimer = null;
let previewRequest = null;
const klineCache = new Map();
let klineNavCodes = [];
let klineNavIndex = -1;
// 旗杆日图标 + 当天消息提示（仅小旗杆面板的 K 线按钮带 data-flag-date）
let klineNavFlagDates = [];
let currentFlagDate = '';      // 当前 K 线对应股票的旗杆日 YYYYMMDD，非小旗杆为空
let flagIconHit = null;        // 主画布上小旗图标命中区 {x, y, r, index}
let chartGeom = null;          // 主画布几何信息，供鼠标反查蜡烛序号
let msgTimer = null;
let msgLoadingKey = '';        // 正在请求中的 code|date，防重复发请求
let msgShownKey = '';          // 已渲染的 code|date，防 mousemove 高频重建 DOM
const msgCache = new Map();
const msgBox = document.getElementById('kline-msg');
// 记录来源列表（按当前排序后的 DOM 顺序），供 ▲▼ / PgUp/PgDn 切换上下只股票
function setKlineNav(triggerEl, code) {
    const table = triggerEl && triggerEl.closest ? triggerEl.closest('table') : null;
    if (table) {
        const buttons = Array.from(table.querySelectorAll('.kline-trigger'))
            .filter(b => b.dataset.code);
        klineNavCodes = buttons.map(b => b.dataset.code);
        klineNavFlagDates = buttons.map(b => b.dataset.flagDate || '');
        klineNavIndex = klineNavCodes.indexOf(code);
    } else {
        klineNavCodes = []; klineNavFlagDates = []; klineNavIndex = -1;
    }
    updateKlineNav();
}
function updateKlineNav() {
    const prev = document.getElementById('stock-prev');
    const next = document.getElementById('stock-next');
    const n = klineNavCodes.length;
    const hasNav = n > 0 && klineNavIndex >= 0;
    prev.disabled = !hasNav;
    next.disabled = !hasNav;
    if (!hasNav) {
        prev.textContent = next.textContent = '–';
        prev.title = next.title = '';
        prev.setAttribute('aria-label', '上一只股票（PgUp）');
        next.setAttribute('aria-label', '下一只股票（PgDn）');
        return;
    }
    // 到顶/到底循环，按钮显示跳转后的目标序号（1 基）
    const p = (klineNavIndex - 1 + n) % n;
    const x = (klineNavIndex + 1) % n;
    prev.textContent = p + 1;
    next.textContent = x + 1;
    prev.title = `上一只：第${p + 1}支（共${n}支，PgUp）`;
    next.title = `下一只：第${x + 1}支（共${n}支，PgDn）`;
    prev.setAttribute('aria-label', `上一只股票，第${p + 1}支（共${n}支）`);
    next.setAttribute('aria-label', `下一只股票，第${x + 1}支（共${n}支）`);
}
async function stepKlineStock(delta) {
    const n = klineNavCodes.length;
    if (!n || klineNavIndex < 0) return;
    klineNavIndex = (klineNavIndex + delta + n) % n;
    currentFlagDate = klineNavFlagDates[klineNavIndex] || '';
    updateKlineNav();
    await openKline(klineNavCodes[klineNavIndex], null, true);
}
async function openKline(code, triggerEl, keepNav = false) {
    if (!keepNav) {
        setKlineNav(triggerEl, code);
        lastChartButton = triggerEl || document.activeElement;
        // 只有小旗杆面板的按钮带 data-flag-date，其余来源（搜索/年度翻倍）无旗杆日
        currentFlagDate = (triggerEl && triggerEl.dataset && triggerEl.dataset.flagDate) || '';
        hideFlagMsg();
    }
    currentChartCode = code;
    if (!keepNav) currentChartDays = 120;
    currentChartLatest = false;
    currentChartEndDate = '0';
    updateRangeControls();
    overlay.classList.add('open'); statusEl.style.display = 'grid'; statusEl.textContent = '正在加载行情…';
    // 焦点移入面板（非按钮），使 Enter 命中全局快捷键而非原生激活表格里的 K线按钮
    overlay.focus({ preventScroll: true });
    document.getElementById('chart-title').textContent = code + ' K线';
    document.getElementById('chart-meta').textContent = `最近${currentChartDays}个交易日`;
    try {
        const data = await fetchKline(code, null, currentChartDays, '0');
        if (!data.items.length) throw new Error('该日期前没有可显示的日线数据');
        document.getElementById('chart-title').textContent = `${code} ${data.name || ''}`;
        currentChartItems = data.items;
        currentChartEndDate = data.items[data.items.length - 1].date;
        setKlineMeta(currentChartDays, data);
        updateDateControls();
        statusEl.style.display = 'none'; drawKline(currentChartItems);
    } catch (error) { statusEl.textContent = error.message; }
}
async function showLatestKline() {
    if (!currentChartCode) return;
    const button = document.getElementById('chart-latest');
    if (button.disabled) return;   // 连按 Enter 时不重复发起请求
    button.disabled = true; statusEl.style.display = 'grid'; statusEl.textContent = '正在加载最新行情…';
    try {
        const response = await fetch(`/api/kline/${encodeURIComponent(currentChartCode)}?days=${currentChartDays}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '行情请求失败');
        if (!data.items.length) throw new Error('没有可显示的日线数据');
        currentChartItems = data.items;
        currentChartLatest = true;
        currentChartEndDate = data.items[data.items.length - 1].date;
        updateDateControls();
        setKlineMeta(currentChartDays, data, ` · 更新至 ${data.items[data.items.length - 1].date}`);
        statusEl.style.display = 'none'; drawKline(currentChartItems);
    } catch (error) { statusEl.textContent = error.message; }
    finally { button.disabled = false; }
}
async function shiftKlineDate(direction) {
    if (!currentChartCode || !currentChartEndDate) return;
    const button = document.getElementById(direction < 0 ? 'date-prev' : 'date-next');
    button.disabled = true; statusEl.style.display = 'grid'; statusEl.textContent = direction < 0 ? '正在加载前一交易日…' : '正在加载后一交易日…';
    try {
        const response = await fetch(`/api/kline/${encodeURIComponent(currentChartCode)}/shift?days=${currentChartDays}&end_date=${currentChartEndDate}&direction=${direction}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '行情请求失败');
        if (!data.items.length) throw new Error('没有可显示的日线数据');
        currentChartItems = data.items;
        currentChartEndDate = data.items[data.items.length - 1].date;
        currentChartLatest = currentChartEndDate === '0';
        setKlineMeta(currentChartDays, data, ` · 截止 ${currentChartEndDate}`);
        statusEl.style.display = 'none'; drawKline(currentChartItems); updateDateControls();
    } catch (error) { statusEl.textContent = error.message; }
    finally { updateDateControls(); }
}
function updateDateControls() {
    document.getElementById('date-next').disabled = !currentChartEndDate || currentChartEndDate >= '0';
    document.getElementById('date-prev').disabled = !currentChartEndDate;
}
// 实际K线数少于请求天数时，说明该股历史不足，提示已达数据上限
function setKlineMeta(days, data, suffix = '') {
    const el = document.getElementById('chart-meta');
    const have = data.items.length;
    const base = `最近${days}个交易日`;
    if (have >= days) {
        el.textContent = base + suffix;
        el.style.color = '';
        return;
    }
    const first = have ? data.items[0].date : '';
    el.textContent = `${base} · 该股仅${have}根K线${first ? `（始于${first}）` : ''}，已达数据上限` + suffix;
    el.style.color = '#d46b08';
}
async function changeKlineRange(delta) {
    const nextDays = Math.max(60, Math.min(240, currentChartDays + delta));
    if (nextDays === currentChartDays || !currentChartCode) return;
    currentChartDays = nextDays; updateRangeControls();
    statusEl.style.display = 'grid'; statusEl.textContent = `正在加载${currentChartDays}个交易日…`;
    try {
        const endDate = currentChartLatest ? '' : currentChartEndDate;
        const data = await fetchKline(currentChartCode, null, currentChartDays, endDate);
        if (!data.items.length) throw new Error('没有可显示的日线数据');
        currentChartItems = data.items;
        setKlineMeta(currentChartDays, data, currentChartLatest ? ` · 更新至 ${data.items[data.items.length - 1].date}` : '');
        statusEl.style.display = 'none'; drawKline(currentChartItems);
    } catch (error) { statusEl.textContent = error.message; }
}
function updateRangeControls() {
    document.getElementById('range-label').textContent = currentChartDays + '日';
    document.getElementById('range-more').disabled = currentChartDays >= 240;
    document.getElementById('range-less').disabled = currentChartDays <= 60;
}
function closeKline() { overlay.classList.remove('open'); hideFlagMsg(); if (lastChartButton) lastChartButton.focus(); }
document.addEventListener('keydown', event => {
    if (!overlay.classList.contains('open')) return;
    if (event.key === 'Escape') { closeKline(); return; }
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const tag = (event.target && event.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    if (event.key === 'PageUp') { event.preventDefault(); stepKlineStock(-1); }
    else if (event.key === 'PageDown') { event.preventDefault(); stepKlineStock(1); }
    else if (event.key === 'Enter') {
        // 焦点在按钮/链接上时交给浏览器原生激活，避免与该元素自身的 Enter 重复触发
        if (tag === 'button' || tag === 'a') return;
        event.preventDefault();
        showLatestKline();
    }
});
async function fetchKline(code, signal, days = 120, endDate = '0') {
    const cacheKey = `${code}|${days}|${endDate || 'latest'}`;
    if (klineCache.has(cacheKey)) return klineCache.get(cacheKey);
    const endParam = endDate ? `&end_date=${encodeURIComponent(endDate)}` : '';
    const response = await fetch(`/api/kline/${encodeURIComponent(code)}?days=${days}${endParam}`, {signal});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '行情请求失败');
    klineCache.set(cacheKey, data);
    return data;
}
function positionPreview(button) {
    const rect = button.getBoundingClientRect(), width = 430, height = 258, gap = 8;
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    const top = rect.bottom + height + gap <= window.innerHeight ? rect.bottom + gap : rect.top - height - gap;
    preview.style.left = left + 'px'; preview.style.top = Math.max(8, top) + 'px';
}
function schedulePreview(button) {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => showPreview(button), 180);
}
async function showPreview(button) {
    const code = button.dataset.code;
    previewRequest?.abort(); previewRequest = new AbortController();
    positionPreview(button); preview.classList.add('open'); preview.setAttribute('aria-hidden', 'false');
    document.getElementById('preview-title').textContent = code + ' · 最近120个交易日';
    previewStatus.style.display = 'grid'; previewStatus.textContent = '正在加载…';
    try {
        const data = await fetchKline(code, previewRequest.signal);
        previewStatus.style.display = 'none'; drawKline(data.items, previewCanvas);
    } catch (error) { if (error.name !== 'AbortError') previewStatus.textContent = error.message; }
}
function hidePreview() {
    clearTimeout(previewTimer); previewRequest?.abort(); previewRequest = null;
    preview.classList.remove('open'); preview.setAttribute('aria-hidden', 'true');
}
document.querySelectorAll('.kline-preview-trigger').forEach(button => {
    button.addEventListener('mouseenter', () => schedulePreview(button));
    button.addEventListener('mouseleave', hidePreview);
    button.addEventListener('focus', () => schedulePreview(button));
    button.addEventListener('blur', hidePreview);
});
function bindPreviewTriggers(root = document) {
    root.querySelectorAll('.kline-preview-trigger:not([data-preview-bound])').forEach(button => {
        button.dataset.previewBound = '1';
        button.addEventListener('mouseenter', () => schedulePreview(button));
        button.addEventListener('mouseleave', hidePreview);
        button.addEventListener('focus', () => schedulePreview(button));
        button.addEventListener('blur', hidePreview);
    });
}
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}
async function loadYearlyDouble() {
    const note = document.getElementById('yearly-double-note');
    const empty = document.getElementById('yearly-double-empty');
    const wrap = document.getElementById('yearly-double-table-wrap');
    const body = document.getElementById('yearly-double-body');
    const runBtn = document.getElementById('yearly-double-run');
    if (runBtn) {
        if (runBtn.disabled) return;
        runBtn.disabled = true;
        runBtn.textContent = '扫描中…';
    }
    try {
        const response = await fetch('/api/yearly-double');
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || '年度翻倍股请求失败');
        document.getElementById('yearly-double-count').textContent = result.count;
        document.getElementById('yearly-double-tab-count').textContent = result.count;
        note.textContent = `区间 ${result.start_date} 至 ${result.end_date}，按“先出现区间最低价 low，之后最高价 high 至少达到 2 倍”筛选；共扫描 ${result.scanned} 只股票，默认展示涨幅最高的前 ${result.items.length} 只。`;
        if (!result.items.length) {
            empty.textContent = '最近一年没有符合“低点后高点翻倍”的股票。';
            return;
        }
        body.innerHTML = result.items.map((r, index) => `
            <tr>
                <td>${index + 1}</td>
                <td class="code"><a href="${escapeHtml(r.eastmoney_url || '#')}" target="_blank" rel="noopener">${escapeHtml(r.st_code)}</a><button class="kline-trigger" data-code="${escapeHtml(r.st_code)}" onclick="openKline('${escapeHtml(r.st_code)}', this)">K线</button><button class="kline-preview-trigger" data-code="${escapeHtml(r.st_code)}" type="button">预览</button></td>
                <td>${escapeHtml(r.name)}</td>
                <td>${escapeHtml(r.low_date)}</td>
                <td>${Number(r.low_price).toFixed(2)}</td>
                <td>${escapeHtml(r.high_date)}</td>
                <td>${Number(r.high_price).toFixed(2)}</td>
                <td><span class="tag tag-red">${Number(r.gain_pct).toFixed(1)}%</span></td>
                <td>${r.latest_close != null ? Number(r.latest_close).toFixed(2) : '-'}</td>
                <td>${r.gain_since_pct != null ? `<span class="tag tag-red">${Number(r.gain_since_pct).toFixed(1)}%</span>` : '-'}</td>
                <td>${r.high_drawdown_pct != null ? `<span class="tag tag-orange">${Number(r.high_drawdown_pct).toFixed(1)}%</span>` : '-'}</td>
            </tr>`).join('');
        empty.style.display = 'none';
        wrap.style.display = 'block';
        bindPreviewTriggers(wrap);
        if (runBtn) runBtn.textContent = '重新扫描';
    } catch (error) {
        empty.textContent = error.message;
        empty.style.display = 'block';
        if (runBtn) runBtn.textContent = '扫描年度翻倍股';
    } finally {
        if (runBtn) runBtn.disabled = false;
    }
}
// 年度翻倍股默认不查询，仅在点击面板内按钮后触发
let suggestTimer = null;
let latestCandidates = [];
let activeSuggestIndex = -1;
function closeSuggest() {
    const box = document.getElementById('stock-suggest');
    if (box) { box.style.display = 'none'; box.innerHTML = ''; }
    activeSuggestIndex = -1;
}
function chooseCandidate(code) {
    const input = document.getElementById('stock-code-input');
    input.value = code;
    closeSuggest();
    queryStockChart();
}
function renderCandidates(items, keyword) {
    const box = document.getElementById('stock-suggest');
    if (!items.length) { box.innerHTML = '<div style="padding:10px 12px;color:#888;">未找到匹配股票</div>'; box.style.display = 'block'; return; }
    latestCandidates = items;
    box.innerHTML = items.map((item, index) => {
        const simpleCode = escapeHtml(item.code);
        const left = index === activeSuggestIndex ? 'background:#f0f5ff;' : '';
        return `<div role="option" data-index="${index}" onmousedown="chooseCandidate('${simpleCode}')" style="display:flex;justify-content:space-between;gap:8px;padding:8px 12px;cursor:pointer;${left}">
            <span><strong>${simpleCode}</strong> ${escapeHtml(item.name)}</span>
            <span style="color:#1677ff;font-size:12px;">查看K线</span>
        </div>`;
    }).join('');
    box.style.display = 'block';
}
async function fetchCandidates(keyword) {
    if (!keyword || keyword.length < 1) { closeSuggest(); return; }
    const response = await fetch(`/api/search-stock?q=${encodeURIComponent(keyword)}`);
    if (!response.ok) return;
    const items = await response.json();
    renderCandidates(items, keyword);
}
async function queryStockChart() {
    const input = document.getElementById('stock-code-input');
    const resultEl = document.getElementById('stock-query-result');
    const raw = (input.value || '').trim();
    if (!raw) { resultEl.innerHTML = '<span class="empty">请输入代码或名称，例如 000001.SZ / 贵州茅台 / 平安</span>'; return; }
    if (latestCandidates.length && activeSuggestIndex >= 0 && activeSuggestIndex < latestCandidates.length) {
        chooseCandidate(latestCandidates[activeSuggestIndex].code);
        return;
    }
    let code = raw.toUpperCase();
    if (/^\d{6}$/.test(code)) code = code + '.SZ';
    if (!/^\d{6}\.(SZ|SH|BJ)$/.test(code)) { resultEl.innerHTML = '请输入完整代码或股票名称后从候选中选择。'; return; }
    closeSuggest();
    resultEl.innerHTML = '正在查询…';
    try {
        const data = await fetchKline(code);
        if (!data.items.length) { resultEl.innerHTML = '未查询到可展示的日线数据'; return; }
        const lastItem = data.items[data.items.length - 1];
        resultEl.innerHTML = `
            <span>${escapeHtml(data.name || '-')}</span>
            <span class="tag tag-blue ml-2">${escapeHtml(code)}</span>
            <span class="ml-2">最新: ${escapeHtml(lastItem.date)} 收盘 ${Number(lastItem.close).toFixed(2)}</span>
            <button class="kline-trigger ml-2" onclick="openKline('${escapeHtml(code)}')">查看K线</button>
        `;
        openKline(code);
    } catch (error) {
        resultEl.innerHTML = '查询失败：' + escapeHtml(error.message);
    }
}
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('stock-code-input');
    input.addEventListener('input', () => {
        clearTimeout(suggestTimer);
        activeSuggestIndex = -1;
        suggestTimer = setTimeout(() => fetchCandidates((input.value || '').trim()), 220);
    });
    input.addEventListener('keydown', (event) => {
        if (!latestCandidates.length && event.key !== 'Escape') return;
        if (event.key === 'ArrowDown') { activeSuggestIndex = Math.min(activeSuggestIndex + 1, latestCandidates.length - 1); renderCandidates(latestCandidates, input.value); event.preventDefault(); }
        else if (event.key === 'ArrowUp') { activeSuggestIndex = Math.max(activeSuggestIndex - 1, 0); renderCandidates(latestCandidates, input.value); event.preventDefault(); }
        else if (event.key === 'Escape') { closeSuggest(); }
    });
    input.addEventListener('blur', () => setTimeout(closeSuggest, 180));
});
function drawKline(items, targetCanvas = canvas) {
    const dpr = window.devicePixelRatio || 1, rect = targetCanvas.getBoundingClientRect();
    targetCanvas.width = rect.width * dpr; targetCanvas.height = rect.height * dpr;
    const ctx = targetCanvas.getContext('2d'); ctx.scale(dpr, dpr);
    const w=rect.width,h=rect.height,left=58,right=18,top=18,priceBottom=h*.72,volTop=h*.78,bottom=h-28;
    const highs=items.map(x=>x.high), lows=items.map(x=>x.low), vols=items.map(x=>x.volume);
    const maxP=Math.max(...highs), minP=Math.min(...lows), maxV=Math.max(...vols), range=maxP-minP||1;
    const y=p=>top+(maxP-p)/range*(priceBottom-top), step=(w-left-right)/items.length, body=Math.max(2,Math.min(9,step*.58));
    ctx.font='11px Cascadia Code, Consolas, monospace'; ctx.strokeStyle='#edf0f2'; ctx.fillStyle='#888'; ctx.lineWidth=1;
    for(let i=0;i<=4;i++){const yy=top+(priceBottom-top)*i/4;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(w-right,yy);ctx.stroke();ctx.fillText((maxP-range*i/4).toFixed(2),4,yy+4);}
    items.forEach((d,i)=>{const x=left+step*(i+.5),up=d.close>=d.open,color=up?'#cf1322':'#389e0d';ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x,y(d.high));ctx.lineTo(x,y(d.low));ctx.stroke();const yo=y(Math.max(d.open,d.close)),bh=Math.max(1,Math.abs(y(d.open)-y(d.close)));ctx.fillRect(x-body/2,yo,body,bh);const vh=(d.volume/maxV)*(bottom-volTop);ctx.globalAlpha=.48;ctx.fillRect(x-body/2,bottom-vh,body,vh);ctx.globalAlpha=1;});
    ctx.fillStyle='#888'; const labels=[0,Math.floor((items.length-1)/2),items.length-1]; labels.forEach(i=>{const x=left+step*(i+.5);ctx.fillText(items[i].date.slice(4,6)+'-'+items[i].date.slice(6,8),x-15,h-8);});
    ctx.fillText('成交量',4,volTop+10);
    // 旗杆日：高亮该日蜡烛，并在最高价上方画小旗图标（仅主画布，预览不画）
    if (targetCanvas !== canvas) return;
    chartGeom = {left, step, top, priceBottom, count: items.length};
    flagIconHit = null;
    if (!currentFlagDate) return;
    const fi = items.findIndex(d => d.date === currentFlagDate);
    if (fi < 0) return;
    const fx = left + step * (fi + .5);
    ctx.save();
    ctx.fillStyle = 'rgba(250,140,22,.10)';
    ctx.fillRect(fx - step / 2, top, step, priceBottom - top);
    const ix = fx, iy = Math.max(top + 11, y(items[fi].high) - 19);
    ctx.beginPath(); ctx.arc(ix, iy, 9.5, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,255,255,.96)'; ctx.fill();
    ctx.strokeStyle = '#fa8c16'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.beginPath(); ctx.moveTo(ix - 3.5, iy - 6.5); ctx.lineTo(ix - 3.5, iy + 6.5);
    ctx.strokeStyle = '#d46b08'; ctx.lineWidth = 2; ctx.stroke();
    ctx.beginPath(); ctx.moveTo(ix - 3, iy - 6); ctx.lineTo(ix + 6, iy - 2.5);
    ctx.lineTo(ix - 3, iy + 1); ctx.closePath();
    ctx.fillStyle = '#fa8c16'; ctx.fill();
    ctx.restore();
    flagIconHit = {x: ix, y: iy, r: 10, index: fi};
}
// ---- 旗杆日悬停：展示当天重要消息（东财公告，按 code|date 缓存）----
function fmtFlagDate(value) { return value ? `${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)}` : ''; }
function hideFlagMsg() { clearTimeout(msgTimer); msgTimer = null; if (msgBox) msgBox.hidden = true; }
function hideFlagMsgSoon() { if (!msgBox || msgBox.hidden) return; clearTimeout(msgTimer); msgTimer = setTimeout(hideFlagMsg, 140); }
function positionFlagMsg() {
    if (!msgBox || msgBox.hidden || !flagIconHit) return;
    const width = msgBox.offsetWidth, height = msgBox.offsetHeight;
    const stageW = msgBox.parentElement.clientWidth, stageH = msgBox.parentElement.clientHeight;
    let leftPos = flagIconHit.x + 16, topPos = flagIconHit.y - 10;
    if (leftPos + width > stageW - 6) leftPos = flagIconHit.x - width - 16;
    leftPos = Math.max(6, Math.min(leftPos, stageW - width - 6));
    topPos = Math.max(6, Math.min(topPos, stageH - height - 6));
    msgBox.style.left = leftPos + 'px';
    msgBox.style.top = topPos + 'px';
}
function renderFlagMsg(items, failedMessage = '') {
    const head = `<div class="kline-msg-title">旗杆日 ${fmtFlagDate(currentFlagDate)} · 当天重要消息（${items.length}条）</div>`;
    if (failedMessage) {
        msgBox.innerHTML = head + `<div class="kline-msg-empty">消息加载失败：${escapeHtml(failedMessage)}</div>`;
    } else if (!items.length) {
        msgBox.innerHTML = head + '<div class="kline-msg-empty">当天没有公告</div>';
    } else {
        msgBox.innerHTML = head + '<ul>' + items.map(item =>
            `<li><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a></li>`
        ).join('') + '</ul>';
    }
    msgShownKey = `${currentChartCode}|${currentFlagDate}`;
    msgBox.hidden = false;
    positionFlagMsg();
}
async function loadFlagMessages() {
    const code = currentChartCode, day = currentFlagDate;
    if (!code || !day) return;
    const key = `${code}|${day}`;
    if (msgCache.has(key)) { renderFlagMsg(msgCache.get(key)); return; }
    if (msgLoadingKey === key) return;   // 同一条消息只发一次请求
    msgLoadingKey = key;
    msgBox.innerHTML = `<div class="kline-msg-title">旗杆日 ${fmtFlagDate(day)} · 当天重要消息</div><div class="kline-msg-empty">正在加载…</div>`;
    msgBox.hidden = false;
    positionFlagMsg();
    try {
        const response = await fetch(`/api/messages/${encodeURIComponent(code)}/${day}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '消息请求失败');
        msgCache.set(key, data.items);
        if (currentChartCode === code && currentFlagDate === day) renderFlagMsg(data.items);
    } catch (error) {
        if (currentChartCode === code && currentFlagDate === day) renderFlagMsg([], error.message);
    } finally {
        msgLoadingKey = '';
    }
}
function showFlagMsg() {
    clearTimeout(msgTimer); msgTimer = null;
    // 已在展示同一股票同一日则不重复渲染，避免 mousemove 高频重建 DOM
    if (msgShownKey === `${currentChartCode}|${currentFlagDate}` && !msgBox.hidden) return;
    loadFlagMessages();
}
canvas.addEventListener('mousemove', event => {
    if (!currentFlagDate || !chartGeom || !flagIconHit) { hideFlagMsgSoon(); return; }
    const rect = canvas.getBoundingClientRect();
    const mx = event.clientX - rect.left, my = event.clientY - rect.top;
    const idx = Math.round((mx - chartGeom.left) / chartGeom.step - .5);
    const onFlagDay = idx >= 0 && idx < chartGeom.count && idx === flagIconHit.index;
    const onIcon = Math.hypot(mx - flagIconHit.x, my - flagIconHit.y) <= flagIconHit.r + 4;
    if (onFlagDay || onIcon) showFlagMsg(); else hideFlagMsgSoon();
});
canvas.addEventListener('mouseleave', event => {
    if (event.relatedTarget && msgBox.contains(event.relatedTarget)) return;
    hideFlagMsgSoon();
});
msgBox.addEventListener('mouseenter', () => { clearTimeout(msgTimer); msgTimer = null; });
msgBox.addEventListener('mouseleave', hideFlagMsg);
window.addEventListener('resize', () => { hideFlagMsg(); if (overlay.classList.contains('open') && currentChartItems.length) drawKline(currentChartItems); });
