# AGENTS.md

## Project overview

Chinese A-share stock market data loader and screening strategies. Python 3.9, no `requirements.txt` — dependencies are `tushare`, `pymysql`, `mysql.connector`, `fastapi`, `pydantic`, `openpyxl`, `pandas`.

## Two coexisting codebases

The repo has two independent database approaches that are **not interchangeable**:

| Layer | Files | DB driver | Database | Table layout |
|-------|-------|-----------|----------|--------------|
| Newer | `loadStocks.py`, `StockApplication.py` | `pymysql` | `stockshare` | Per-stock tables: `gp{symbol}` (e.g. `gp000001`) |
| Older | `stockPolicy.py`, `stockPolicy_obsolete.py` | `mysql.connector` | `sm` | Centralized: `st_basic`, `st_daily` |

`stockPolicy_obsolete.py` is the predecessor of `stockPolicy.py`. Most functions are duplicated; `stockPolicy.py` adds DB-backed variants (`getFanbeigu` using SQL vs the API-only version).

## Running

```bash
# Activate venv first
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac

# Data loading (newer codebase)
python StockApplication.py

# FastAPI server (scaffold only, not wired to stock logic)
uvicorn main:app --reload
```

No tests, no linting, no CI configured.

## MySQL prerequisites

Both codebases require a local MySQL instance. Credentials are hardcoded — no `.env` or config file:

- `stockshare` DB: user=`root`, password=`P@ssw0rd` (`loadStocks.py`)
- `sm` DB: user=`root`, password=`1234` (`stockPolicy.py`)

Schema must be created manually before running. `loadStocks.py` creates per-stock tables automatically; `stockPolicy.py` expects `st_basic` and `st_daily` to already exist.

## Tushare API

- Token stored as `TUSHARE_TOKEN` constant at top of each file.
- `pro.stock_basic()` — limited to ~5 calls/day.
- `pro.pro_bar()` — rate-limited to 200 calls/minute. Functions sleep 5 seconds every 100 records to avoid throttling.
- Date format: `YYYYMMDD` strings (e.g. `'20260130'`).

## SQL notes

- `loadStocks.py`: values use parameterized queries (`cursor.execute(sql, params)`). Table names use `_escape_table_name()` backtick wrapping.
- `stockPolicy.py` / `stockPolicy_obsolete.py`: use `mysql.connector` parameterized queries for values. No table name interpolation (fixed schema).
- Table names in `loadStocks.py` are derived from stock symbols (`gp{symbol}`) — safe alphanumeric, but always use `_escape_table_name()`.

## Internal helpers (stockPolicy*.py)

- `_get_stock_basic()` — lazy-loads and caches `stock_basic` DataFrame (avoids module-level API calls).
- `_default_stock_list()` — returns `df.ts_code` from the cached basic data.
- `_should_skip(df, i, startDate)` — shared filter: excludes 688/ST/*ST/listings after 20210101.

## Key function locations

- `loadStocks.py:connectDB` — DB connection for newer codebase
- `loadStocks.py:getStockBasic` — fetch all listed stock basics from Tushare
- `loadStocks.py:createStockTable` — create per-stock daily data tables
- `loadStocks.py:insertNewTransactonRecordForAllStocks` — bulk load daily transaction data
- `stockPolicy.py:getFanbeigu` — find stocks that gained `multiple`x (DB-backed, faster)
- `stockPolicy.py:getJuliangshangzhang` — find stocks with volume spike + price surge patterns
- `stockPolicy.py:getxiangshangtiaokongquekou` — gap-up screener (excludes 688/ST/new listings)

## Conventions

- Chinese comments throughout — preserve them when editing.
- Date params default to today via `time.strftime("%Y%m%d")` when empty.
- Stock filtering pattern: exclude `688*` (STAR board), `ST`/`*ST` names, and listings after `20210101`.
- `main.py` is a FastAPI placeholder — the `/items/` endpoints are not related to stock functionality.
