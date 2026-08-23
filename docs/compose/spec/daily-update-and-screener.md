---
feature: daily-update-and-screener
status: delivered
updated: 2026-08-23
branch: feature/daily-update-screener
commits: 
---

# 每日数据更新 + 放量涨幅筛选

## Report

**What was built** — 两个功能模块 + 额外的 Web 筛选系统：

1. `dailyUpdate.py`：每日自动执行 `getStockBasic → loadAllBasic → createStockTable → insertNewTransactonRecordForAllStocks → buildDailyTable → getLiangJiaFangLiang` 流程（6步），带日志输出到 `logs/daily_update.log`。配合 `setup_task.bat` 一键注册 Windows 定时任务（每日 20:00）。

2. `stockPolicy.py` 新增三个函数：
   - `createDailyTable()` — 创建 `st_daily` 汇总表
   - `buildDailyTable(startDate, endDate)` — 将所有 `gp{symbol}` 表的日线数据汇总到 `st_daily`，支持 symbol→ts_code 映射（优先 stocks 表，回退 tushare API，最终规则映射）
   - `createSignalTable()` — 创建 `st_daily_signal` 表（按 spec 定义的结构）
   - `getLiangJiaFangLiang(startDate, endDate)` — 基于 `st_daily` 表 SQL 联查，筛选当日成交量≥前日3倍且涨幅>6%的股票，排除科创板/ST/次新股，结果去重写入 `st_daily_signal` 表

3. `StockApplication.py` 追加了筛选函数调用示例（T6）

4. 额外实现（不在原 spec 中）：
   - `main.py`：FastAPI Web 服务，提供跳空放量涨幅策略的可视化页面
   - `run_strategy_combined.py`：独立命令行筛选脚本
   - `compare_strategies.py`：双策略对比分析工具

**Files touched**: `stockPolicy.py`（新增 createDailyTable/buildDailyTable/createSignalTable/getLiangJiaFangLiang）、`dailyUpdate.py`（追加步骤5/6）、`StockApplication.py`（追加调用示例）、`main.py`（新建）、`templates/combined.html`（新建）、`run_strategy_combined.py`（新建）、`compare_strategies.py`（新建）、`docs/compose/spec/daily-update-and-screener.md`（更新）

## [S1] Problem
用户需要两个自动化能力：
1. 每天自动更新股票基础信息和建表，目前只能手动运行 `StockApplication.py`。
2. 自动筛选当前日期的当日成交量≥前日3倍且涨幅>6%的股票，并持久化结果便于后续追踪。

## [S2] Design

### S2.1 每日数据更新脚本

新建 `dailyUpdate.py`，复用 `loadStocks.py` 已有函数，按顺序执行：
1. `getStockBasic()` — 获取最新股票列表
2. `loadAllBasic(df)` — 增量写入 `stockshare.stocks` 总表
3. `createStockTable(df)` — 为新股票创建 `gp{symbol}` 日线表
4. **（超出原设计）** `insertNewTransactonRecordForAllStocks(df, start_date, end_date)` — 自动加载近7天日线数据

运行日志输出到 `logs/daily_update.log`（自动创建 logs 目录）。

**定时调度**：通过 Windows 任务计划程序（schtasks）注册，每日 20:00 执行。

### S2.2 放量涨幅筛选函数

在 `stockPolicy.py` 中新增函数 `getLiangJiaFangLiang(startDate='', endDate='')`：
- 基于 `st_daily` 表进行 SQL 联查（两个交易日对比）
- 筛选逻辑：当日成交量 ≥ 前日成交量 × 3，且当日涨幅（pct_chg）> 6%
- 排除科创板(688)；若 tushare stock_basic 可用，额外排除 ST/*ST 和次新股（`_should_skip`）
- 结果去重写入 `st_daily_signal` 表（INSERT IGNORE，依赖 trade_date + st_code 唯一键）

辅助函数：
- `createDailyTable()` — 创建 `st_daily` 汇总表（ts_code, symbol, trade_date, OHLC, pct_chg, vol, amount）
- `buildDailyTable(startDate, endDate)` — 从所有 `gp{symbol}` 表汇总日线数据到 `st_daily`，symbol→ts_code 映射三级回退：stocks 表 → tushare API → 规则映射

**筛选 SQL 核心逻辑**：
```sql
SELECT a.ts_code, a.trade_date, a.closep, a.pct_chg, a.vol,
       b.vol AS prev_vol, ROUND(a.vol / b.vol, 2) AS vol_ratio
FROM st_daily a
JOIN st_daily b ON a.ts_code = b.ts_code
WHERE a.trade_date = <今日> AND b.trade_date = <前一交易日>
  AND a.vol >= b.vol * 3
  AND a.pct_chg > 6
```

### S2.3 结果存储表 `st_daily_signal`

已实现。`createSignalTable()` 创建表结构如下：

```sql
CREATE TABLE IF NOT EXISTS st_daily_signal (
  id INT AUTO_INCREMENT PRIMARY KEY,
  trade_date VARCHAR(8) NOT NULL,
  st_code VARCHAR(12) NOT NULL,
  closePrice FLOAT,
  pct_chg FLOAT,
  vol FLOAT,
  prev_vol FLOAT,
  vol_ratio FLOAT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_code (trade_date, st_code)
);
```

### S2.4 调用入口

已实现。`StockApplication.py` 中追加了筛选函数调用示例：
```python
import stockPolicy as sp
sp.createDailyTable()
sp.createSignalTable()
sp.buildDailyTable(startDate='20260730', endDate='20260822')
result = sp.getLiangJiaFangLiang()
```

## [S3] Out of Scope（原设计）
- 不修改现有 `loadStocks.py` 或 `stockPolicy.py` 中的任何已有函数。
- 不实现 Web 界面或邮件通知。
- 不处理交易日判断（非交易日运行时跳过筛选即可）。
- 不在定时任务中自动加载日线数据（日线数据加载由用户另行触发 `insertNewTransactonRecordForAllStocks`）。

## [S4] Extra Implementation（超出原设计范围）

### S4.1 FastAPI Web 筛选系统 (`main.py`)
- 基于 FastAPI + Jinja2 的 Web 服务，提供跳空放量涨幅策略的可视化页面
- `_run_combined_strategy(date_str)` 实现三策略并行筛选：s1（放量涨幅）、s2（跳空缺口）、combined（三条件同时满足）
- 内存缓存机制（`_cache`），TTL 30 分钟
- 支持通过 `?date=` 参数查看历史日期的筛选结果
- 东方财富股票链接生成（`_eastmoney_url`）
- Web 模板：`templates/combined.html`

### S4.2 独立筛选脚本 (`run_strategy_combined.py`)
- 命令行版本的跳空放量涨幅筛选
- 筛选条件：跳空缺口(今低>昨高) + 放量≥3倍 + 涨幅>6%
- 结果保存到 `跳空放量涨幅_{date}.txt` 文件

### S4.3 策略对比分析工具 (`compare_strategies.py`)
- 双策略对比：放量涨幅 vs 跳空缺口
- 计算重叠率、均值、中位数等统计指标
- 规律分析：重叠组涨幅更高说明"跳空+放量+大涨"是更强信号

## Tasks
- [x] T1: 新建 `dailyUpdate.py` — 包含 `getStockBasic → loadAllBasic → createStockTable` 流程和日志输出 (covers: S2.1)
- [x] T2: 在 `stockPolicy.py` 中新增 `getLiangJiaFangLiang` 函数 — SQL 查询 st_daily，筛选放量+涨幅条件 (covers: S2.2)
- [x] T3: 在 `stockPolicy.py` 中新增 `createSignalTable` 函数 — 创建 `st_daily_signal` 表（如不存在）(covers: S2.3)
- [x] T4: `getLiangJiaFangLiang` 筛选结果写入 `st_daily_signal` 表 — 去重插入（trade_date + st_code 唯一键）(covers: S2.2, S2.3)
- [x] T5: 编写 schtasks 注册脚本 `setup_task.bat` — 注册每日 20:00 的 Windows 定时任务（原设计21:00） (covers: S2.1)
- [x] T6: 在 `StockApplication.py` 中追加筛选函数调用示例 (covers: S2.4)
