---
feature: daily-update-and-screener
status: partial
updated: 2026-08-21
branch: feature/daily-update-screener
commits: 
---

# 每日数据更新 + 放量涨幅筛选

## Report

**What was built** — 两个功能模块 + 额外的 Web 筛选系统：

1. `dailyUpdate.py`：每日自动执行 `getStockBasic → loadAllBasic → createStockTable → insertNewTransactonRecordForAllStocks`（4步流程），带日志输出到 `logs/daily_update.log`。配合 `setup_task.bat` 一键注册 Windows 定时任务（每日 20:00）。**超出原设计**：额外实现了步骤4，自动加载近7天日线数据。

2. 放量涨幅筛选功能**未按原设计实现**于 `stockPolicy.py`。原计划的 `getLiangJiaFangLiang` 函数和 `st_daily_signal` 持久化表均未实现。取而代之，筛选逻辑被实现在以下位置：
   - `main.py`：FastAPI Web 服务，提供跳空放量涨幅策略的可视化页面（含内存缓存）
   - `run_strategy_combined.py`：独立命令行筛选脚本，结果保存到 txt 文件
   - `compare_strategies.py`：放量涨幅 vs 跳空缺口双策略对比分析工具

**Files touched**: `dailyUpdate.py`（新建）、`setup_task.bat`（新建）、`main.py`（新建，FastAPI Web 服务）、`templates/combined.html`（新建，Web 模板）、`run_strategy_combined.py`（新建，独立筛选脚本）、`compare_strategies.py`（新建，策略对比）、`stockPolicy.py`（未修改）、`StockApplication.py`（未追加筛选调用）

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

**原设计（未实现）**：在 `stockPolicy.py` 中新增 `getLiangJiaFangLiang(startDate='', endDate='')`，基于 `sm.st_daily` 表 SQL 查询，结果写入 `st_daily_signal` 表。

**实际实现**：筛选逻辑（成交量≥前日3倍 + 涨幅>6%）分散在多个文件中，均直接查询各股票的 `gp{symbol}` 日线表而非 `st_daily` 表，且结果未持久化到数据库：

- `main.py:_run_combined_strategy(date_str)` — 跳空+放量+涨幅三策略合并，FastAPI 页面展示，带30分钟内存缓存
- `run_strategy_combined.py` — 命令行版，筛选跳空+放量+涨幅同时满足的股票，结果保存到 `跳空放量涨幅_{date}.txt`
- `compare_strategies.py` — 双策略对比分析（放量涨幅 vs 跳空缺口），含统计分析和规律总结

通用过滤条件：排除科创板(688)，但**未实现** `_should_skip` 中的 ST/*ST 和次新股过滤。

**原设计 SQL 核心逻辑**（未使用）：
```sql
SELECT a.st_code, a.trade_date, a.closePrice, a.pct_chg, a.vol,
       b.vol AS prev_vol, ROUND(a.vol / b.vol, 2) AS vol_ratio
FROM st_daily a
JOIN st_daily b ON a.st_code = b.st_code
WHERE a.trade_date = <今日> AND b.trade_date = <前一交易日>
  AND a.vol >= b.vol * 3
  AND a.pct_chg > 6
```

### S2.3 结果存储表 `st_daily_signal`

**未实现**。原设计的表结构如下，但代码中未创建该表，也未有任何写入操作：

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

**未实现**。`StockApplication.py` 未追加筛选函数调用。

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
- [ ] T2: 在 `stockPolicy.py` 中新增 `getLiangJiaFangLiang` 函数 — **未实现**，逻辑分散在 `main.py`/`run_strategy_combined.py`/`compare_strategies.py` 中 (covers: S2.2)
- [ ] T3: 在 `stockPolicy.py` 中新增 `createSignalTable` 函数 — **未实现** (covers: S2.3)
- [ ] T4: `getLiangJiaFangLiang` 筛选结果写入 `st_daily_signal` 表 — **未实现**，结果仅在内存中或写入 txt 文件 (covers: S2.2, S2.3)
- [x] T5: 编写 schtasks 注册脚本 `setup_task.bat` — 注册每日 20:00 的 Windows 定时任务（原设计21:00） (covers: S2.1)
- [ ] T6: 在 `StockApplication.py` 中追加筛选函数调用示例 — **未实现** (covers: S2.4)
