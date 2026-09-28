import json

with open('output/strategy_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

strategies = data['strategies']
summary = data['summary']
update_time = data['update_time']
data_range = data['data_range']

colors = {
    '巨量上涨': '#ff4d4f',
    '向上跳空缺口': '#fa8c16',
    '跳空上涨': '#1677ff',
    '放量日': '#52c41a',
    '区间涨幅30%': '#722ed1'
}

stats_html = ''
tabs_html = ''
tables_html = ''

for i, (name, cnt) in enumerate(summary.items()):
    color = colors.get(name, '#1677ff')
    active = ' active' if i == 0 else ''
    stats_html += f'    <div class="stat-card{active}" style="--accent: {color}" id="stat-{name}" onclick="switchTab(\'{name}\')"><div class="label">{name}</div><div class="value">{cnt}</div></div>\n'
    tabs_html += f'<button class="tab{active}" onclick="switchTab(\'{name}\')" id="tab-{name}" style="--accent: {color}">{name} <span class="badge">{cnt}</span></button>\n'

    items = strategies[name]
    display = 'block' if i == 0 else 'none'
    rows = ''
    for j, item in enumerate(items):
        pct = item['pct_chg']
        pct_class = 'red' if pct > 0 else 'green'
        vr = item['vol_ratio']
        vr_str = f'{vr:.1f}' if vr > 0 else '-'
        date = item['date']
        date_fmt = f'{date[:4]}-{date[4:6]}-{date[6:]}'
        short_name = item['name'][:6] if len(item['name']) > 6 else item['name']
        rows += f'<tr><td>{j+1}</td><td><strong>{item["code"]}</strong></td><td>{short_name}</td><td>{date_fmt}</td><td class="{pct_class}">{pct:+.2f}%</td><td>{vr_str}</td></tr>\n'

    tables_html += f'''
    <div id="panel-{name}" class="panel" style="display: {display}">
      <table>
        <thead><tr><th>#</th><th>代码</th><th>名称</th><th>信号日期</th><th>涨幅</th><th>量比</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    '''

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股策略筛选结果</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #333; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
h1 {{ font-size: 24px; margin-bottom: 6px; }}
.meta {{ color: #888; font-size: 13px; margin-bottom: 20px; }}
.stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
.stat-card {{ background: #fff; border-radius: 10px; padding: 18px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); min-width: 150px; text-align: center; cursor: pointer; transition: all 0.2s; border-left: 4px solid transparent; }}
.stat-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
.stat-card.active {{ border-left-color: var(--accent); }}
.stat-card .label {{ font-size: 13px; color: #888; margin-bottom: 6px; }}
.stat-card .value {{ font-size: 32px; font-weight: 700; color: var(--accent); }}
.tabs {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }}
.tab {{ padding: 8px 20px; border: 1px solid #d9d9d9; border-radius: 20px; background: #fff; cursor: pointer; font-size: 14px; transition: all 0.2s; }}
.tab:hover {{ border-color: var(--accent); color: var(--accent); }}
.tab.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
.badge {{ background: rgba(255,255,255,0.3); padding: 1px 8px; border-radius: 10px; font-size: 12px; margin-left: 4px; }}
.tab.active .badge {{ background: rgba(255,255,255,0.3); }}
.panel {{ display: none; }}
.panel table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
th {{ background: #fafafa; padding: 12px 16px; text-align: left; font-size: 13px; color: #666; border-bottom: 1px solid #f0f0f0; position: sticky; top: 0; }}
td {{ padding: 11px 16px; border-bottom: 1px solid #f0f0f0; font-size: 14px; }}
tr:hover {{ background: #f6f8ff; }}
.red {{ color: #ff4d4f; font-weight: 600; }}
.green {{ color: #52c41a; }}
footer {{ margin-top: 32px; text-align: center; color: #aaa; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <h1>A股策略筛选看板</h1>
  <div class="meta">数据区间: {data_range} &nbsp;|&nbsp; 更新时间: {update_time}</div>
  <div class="stats">
{stats_html}  </div>
  <div class="tabs">
{tabs_html}  </div>
{tables_html}
  <footer>StockMarket Strategy Screener</footer>
</div>
<script>
function switchTab(name) {{
  document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.stat-card').forEach(s => s.classList.remove('active'));
  var panel = document.getElementById('panel-' + name);
  if (panel) panel.style.display = 'block';
  var tab = document.getElementById('tab-' + name);
  if (tab) tab.classList.add('active');
  var stat = document.getElementById('stat-' + name);
  if (stat) stat.classList.add('active');
}}
</script>
</body>
</html>'''

with open('strategy_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('网页已生成: strategy_dashboard.html')
