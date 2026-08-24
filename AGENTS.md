# AGENTS.md

## Project overview

Chinese A-share stock market data loader and screening strategies. Python 3.14, no `requirements.txt` — dependencies are `tushare`, `pymysql`, `mysql.connector`, `fastapi`, `jinja2`, `openpyxl`, `pandas`.

## Architecture

All code uses a single MySQL database `stockshare` with two DB drivers:

| Layer | Files | DB driver | Table layout |
|-------|-------|-----------|--------------|
| Data loading | `loadStocks.py`, `StockApplication.py` | `pymysql` | Per-stock tables: `gp{symbol}` (e.g. `gp000001`) + `stocks` |
| Strategy & signal | `stockPolicy.py` | `mysql.connector` | `st_daily` (汇总), `st_daily_signal` (信号), `st_basic` |
| Web | `main.py` | `pymysql` | Reads `gp{symbol}` + `stocks`, writes `st_daily_signal` |

## Running

```bash
# Activate venv first
venv\Scripts\activate          # Windows

# Data loading
python StockApplication.py

# FastAPI server (stock screening web UI)
uvicorn main:app --reload --port 8000

# Run all strategies (CLI)
python runAllStrategies.py
```

No tests, no linting, no CI configured.

## MySQL prerequisites

Local MySQL instance required. Credentials are hardcoded — no `.env` or config file:

- `stockshare` DB: user=`root`, password=`P@ssw0rd` (all files)

Tables are auto-created by `stockPolicy.py`:
- `createDailyTable()` → `st_daily`
- `createSignalTable()` → `st_daily_signal` (with legacy migration support)
- `loadStocks.py:createStockTable()` → `gp{symbol}` per-stock tables

## Tushare API

- Token stored as `TUSHARE_TOKEN` constant at top of each file.
- `pro.stock_basic()` — limited to ~5 calls/day.
- `pro.pro_bar()` — rate-limited to 200 calls/minute. Functions sleep 5 seconds every 100 records to avoid throttling.
- Date format: `YYYYMMDD` strings (e.g. `'20260130'`).

## SQL notes

- `loadStocks.py`: values use parameterized queries (`cursor.execute(sql, params)`). Table names use `_escape_table_name()` backtick wrapping.
- `stockPolicy.py`: uses `mysql.connector` parameterized queries for values. Dynamic table names (`gp{symbol}`, `st_daily`) use backtick wrapping.
- `main.py`: uses `pymysql` with parameterized queries.

## Key function locations

### loadStocks.py
- `connectDB` — DB connection
- `getStockBasic` — fetch all listed stock basics from Tushare
- `createStockTable` — create per-stock daily data tables
- `insertNewTransactonRecordForAllStocks` — bulk load daily transaction data

### stockPolicy.py
- `createDailyTable()` — create `st_daily` summary table
- `buildDailyTable(startDate, endDate)` — sync `gp{symbol}` data into `st_daily` (incremental)
- `createSignalTable()` — create `st_daily_signal` table with legacy migration
- `_write_signal(st_codes, strategy, trade_date)` — write strategy results to DB + CSV
- `_append_csv(trade_date, rows)` — append to `output/signals_{date}.csv`
- `getLiangJiaFangLiang(startDate, endDate)` — volume≥3x & gain>6% screener
- `gettiaokongshangzhangguo` — gap-up with volume confirmation
- `getJuliangshangzhang` — volume spike + price surge pattern
- `getxiangshangtiaokongquekou` — gap-up screener
- `getStockListByVolumeChange` — volume change screener
- `getLiangzeng` — progressive volume increase screener
- `getFangliangDay0` — volume spike screener
- `getZhangFu` — period gain screener

### main.py
- FastAPI web UI for stock screening strategies
- `_run_combined_strategy(date_str)` — runs 3 strategies: s1 (放量涨幅), s2 (跳空缺口), combined
- `_save_signals(rows, strategy, trade_date)` — write results to DB + CSV
- Startup auto-calls `createSignalTable()`

## Conventions

- Chinese comments throughout — preserve them when editing.
- Date params default to today via `time.strftime("%Y%m%d")` when empty.
- Stock filtering pattern: exclude `688*` (STAR board), `ST`/`*ST` names, and listings after `20210101`.
- All strategy functions auto-persist results to `st_daily_signal` table and `output/` CSV files.
