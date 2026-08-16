---
feature: daily-update-and-screener
status: delivered
updated: 2026-08-15
branch: feature/daily-update-screener
commits: 
---

# 每日数据更新 + 放量涨幅筛选

## Report

**What was built** — 两个新功能：

1. `dailyUpdate.py`：每日自动执行 `getStockBasic → loadAllBasic → createStockTable` 流程，带日志输出到 `logs/daily_update.log`。配合 `setup_task.bat` 一键注册 Windows 定时任务（每日 21:00）。

2. `stockPolicy.py` 新增 `getLiangJiaFangLiang` 函数：基于 `sm.st_daily` 表 SQL 联查，筛选当日成交量≥前日3倍且涨幅>6%的股票，自动排除科创板/ST/次新股，结果去重写入 `st_daily_signal` 表。

**Files touched**: `dailyUpdate.py`（新建）、`setup_task.bat`（新建）、`stockPolicy.py`（追加函数）、`StockApplication.py`（追加调用示例）、`docs/compose/spec/daily-update-and-screener.md`（功能文档）

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

运行日志输出到 `logs/daily_update.log`（自动创建 logs 目录）。

**定时调度**：通过 Windows 任务计划程序（schtasks）注册，每日 21:00 执行。

命令模板：
```
schtasks /create /tn "StockDailyUpdate" /tr "python <项目绝对路径>\dailyUpdate.py" /sc daily /st 21:00
```

### S2.2 放量涨幅筛选函数

在 `stockPolicy.py` 中新增函数 `getLiangJiaFangLiang(startDate='', endDate='')`：
- 基于 `sm` 数据库的 `st_daily` 表进行 SQL 查询
- 筛选逻辑：取最近两个交易日，当日成交量 ≥ 前日成交量 × 3，且当日涨幅（pct_chg）> 6%
- 同时应用通用过滤 `_should_skip`：排除科创板(688)、ST、*ST、次新股
- 结果写入新建表 `st_daily_signal`

**筛选 SQL 核心逻辑**：
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

字段说明：
- `trade_date` — 触发信号的交易日期
- `st_code` — 股票代码（ts_code 格式）
- `closePrice` — 当日收盘价
- `pct_chg` — 当日涨跌幅（%）
- `vol` — 当日成交量
- `prev_vol` — 前一交易日成交量
- `vol_ratio` — 量比（vol/prev_vol）
- `created_at` — 记录创建时间

### S2.4 调用入口

在 `StockApplication.py` 中追加调用筛选函数的示例代码，或由定时任务脚本统一调度。

## [S3] Out of Scope
- 不修改现有 `loadStocks.py` 或 `stockPolicy.py` 中的任何已有函数。
- 不实现 Web 界面或邮件通知。
- 不处理交易日判断（非交易日运行时跳过筛选即可）。
- 不在定时任务中自动加载日线数据（日线数据加载由用户另行触发 `insertNewTransactonRecordForAllStocks`）。

## Tasks
- [x] T1: 新建 `dailyUpdate.py` — 包含 `getStockBasic → loadAllBasic → createStockTable` 流程和日志输出 (covers: S2.1)
- [x] T2: 在 `stockPolicy.py` 中新增 `getLiangJiaFangLiang` 函数 — SQL 查询 st_daily，筛选放量+涨幅条件 (covers: S2.2)
- [x] T3: 在 `stockPolicy.py` 中新增 `createSignalTable` 函数 — 创建 `st_daily_signal` 表（如不存在）(covers: S2.3)
- [x] T4: `getLiangJiaFangLiang` 筛选结果写入 `st_daily_signal` 表 — 去重插入（trade_date + st_code 唯一键）(covers: S2.2, S2.3)
- [x] T5: 编写 schtasks 注册脚本 `setup_task.bat` — 注册每日 21:00 的 Windows 定时任务 (covers: S2.1)
- [x] T6: 在 `StockApplication.py` 中追加筛选函数调用示例 (covers: S2.4)
