"""無前視偏差回測：30 日平緩上漲策略。

訊號於交易日收盤後產生，下一個該股票有行情的交易日以開盤價進場。
輸出逐筆交易 CSV 與按持有期彙總 CSV。
"""

import argparse
import csv
import datetime
import math
import os
import statistics
import time
import uuid
from collections import defaultdict

import pymysql

from stockPolicy import _smooth_uptrend_metrics


DEFAULT_HORIZONS = (5, 10, 20, 60)


def parse_args():
    parser = argparse.ArgumentParser(description="回測 st_daily 的平緩上漲策略")
    parser.add_argument("--start", default="20240101", help="首個訊號日 YYYYMMDD")
    parser.add_argument("--end", default="", help="最後訊號日 YYYYMMDD；預設自動保留最大持有期")
    parser.add_argument("--window", type=int, default=30, help="訊號回看交易日數")
    parser.add_argument("--min-gain", type=float, default=30)
    parser.add_argument("--min-r2", type=float, default=0.8)
    parser.add_argument("--min-up-ratio", type=float, default=0.6)
    parser.add_argument("--max-drawdown", type=float, default=10)
    parser.add_argument("--horizons", default="5,10,20,60", help="持有交易日，以逗號分隔")
    parser.add_argument("--output-dir", default="output/backtest_smooth_uptrend")
    parser.add_argument("--no-db", action="store_true", help="只輸出 CSV，不寫入回測表")
    return parser.parse_args()


def connect_db():
    return pymysql.connect(
        host="localhost", user="root", password="P@ssw0rd", database="stockshare",
        connect_timeout=10, read_timeout=120, write_timeout=30,
    )


def create_backtest_tables(conn):
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS st_backtest_run (
        run_id VARCHAR(36) PRIMARY KEY, strategy VARCHAR(64) NOT NULL,
        start_date VARCHAR(8) NOT NULL, end_date VARCHAR(8) NOT NULL,
        window_days INT NOT NULL, horizons VARCHAR(32) NOT NULL,
        min_gain_pct DOUBLE NOT NULL, min_r_squared DOUBLE NOT NULL,
        min_up_ratio DOUBLE NOT NULL, max_drawdown_pct DOUBLE NOT NULL,
        status VARCHAR(16) NOT NULL, trade_count INT NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP NULL, INDEX idx_strategy_created(strategy,created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS st_backtest_trade (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id VARCHAR(36) NOT NULL,
        ts_code VARCHAR(12) NOT NULL, signal_date VARCHAR(8) NOT NULL,
        entry_date VARCHAR(8) NOT NULL, entry_open DOUBLE NOT NULL,
        horizon INT NOT NULL, exit_date VARCHAR(8) NOT NULL, exit_close DOUBLE NOT NULL,
        return_pct DOUBLE NOT NULL, mfe_pct DOUBLE NOT NULL, mae_pct DOUBLE NOT NULL,
        signal_gain_pct DOUBLE NOT NULL, signal_r_squared DOUBLE NOT NULL,
        signal_up_ratio DOUBLE NOT NULL, signal_max_drawdown_pct DOUBLE NOT NULL,
        UNIQUE KEY uk_run_signal_horizon(run_id,ts_code,signal_date,horizon),
        INDEX idx_run_horizon(run_id,horizon),
        CONSTRAINT fk_backtest_trade_run FOREIGN KEY(run_id) REFERENCES st_backtest_run(run_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS st_backtest_summary (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id VARCHAR(36) NOT NULL,
        period_type VARCHAR(16) NOT NULL, period_value VARCHAR(16) NOT NULL,
        horizon INT NOT NULL, signals INT NOT NULL, win_rate_pct DOUBLE NOT NULL,
        avg_return_pct DOUBLE NOT NULL, median_return_pct DOUBLE NOT NULL,
        p25_return_pct DOUBLE NOT NULL, p75_return_pct DOUBLE NOT NULL,
        avg_mfe_pct DOUBLE NOT NULL, median_mfe_pct DOUBLE NOT NULL,
        avg_mae_pct DOUBLE NOT NULL, median_mae_pct DOUBLE NOT NULL,
        UNIQUE KEY uk_run_period_horizon(run_id,period_type,period_value,horizon),
        CONSTRAINT fk_backtest_summary_run FOREIGN KEY(run_id) REFERENCES st_backtest_run(run_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    conn.commit()


def offset_date(date_text, calendar_days):
    return (datetime.datetime.strptime(date_text, "%Y%m%d").date()
            + datetime.timedelta(days=calendar_days)).strftime("%Y%m%d")


def load_market_data(args, max_horizon):
    conn = connect_db()
    try:
        cursor = conn.cursor()
        latest_end = args.end
        if not latest_end:
            cursor.execute("SELECT MAX(trade_date) FROM st_daily")
            latest_end = cursor.fetchone()[0]
        # 交易日約占日曆日的 5/7；乘 2 預留停牌及長假緩衝。
        query_start = offset_date(args.start, -args.window * 2)
        query_end = offset_date(latest_end, max_horizon * 2)
        cursor.execute(
            "SELECT ts_code,trade_date,openp,high,low,closep "
            "FROM st_daily WHERE openp IS NOT NULL AND high IS NOT NULL "
            "AND low IS NOT NULL AND closep IS NOT NULL "
            "AND trade_date BETWEEN %s AND %s ORDER BY ts_code,trade_date",
            (query_start, query_end),
        )
        grouped = defaultdict(list)
        for code, date, openp, high, low, closep in cursor:
            grouped[code].append((str(date), float(openp), float(high), float(low), float(closep)))
        return grouped
    finally:
        conn.close()


def qualifies(closes, args):
    metrics = _smooth_uptrend_metrics(closes)
    return metrics if (
        metrics
        and metrics["gain_pct"] > args.min_gain
        and metrics["slope"] > 0
        and metrics["r_squared"] >= args.min_r2
        and metrics["up_ratio"] >= args.min_up_ratio
        and metrics["max_drawdown_pct"] <= args.max_drawdown
    ) else None


def run_backtest(series_by_code, args, horizons):
    trades = []
    max_horizon = max(horizons)
    for code, rows in series_by_code.items():
        if code.startswith("688"):
            continue
        dates = [row[0] for row in rows]
        closes = [row[4] for row in rows]
        for signal_idx in range(args.window - 1, len(rows) - max_horizon):
            signal_date = dates[signal_idx]
            if signal_date < args.start or (args.end and signal_date > args.end):
                continue
            metrics = qualifies(closes[signal_idx - args.window + 1:signal_idx + 1], args)
            if not metrics:
                continue
            entry_idx = signal_idx + 1
            entry_price = rows[entry_idx][1]
            if entry_price <= 0:
                continue
            for horizon in horizons:
                exit_idx = entry_idx + horizon - 1
                future = rows[entry_idx:exit_idx + 1]
                exit_close = future[-1][4]
                returns = (exit_close / entry_price - 1) * 100
                mfe = (max(row[2] for row in future) / entry_price - 1) * 100
                mae = (min(row[3] for row in future) / entry_price - 1) * 100
                trades.append({
                    "ts_code": code, "signal_date": signal_date,
                    "entry_date": rows[entry_idx][0], "entry_open": entry_price,
                    "horizon": horizon, "exit_date": future[-1][0],
                    "exit_close": exit_close, "return_pct": returns,
                    "mfe_pct": mfe, "mae_pct": mae,
                    "signal_gain_pct": metrics["gain_pct"],
                    "signal_r_squared": metrics["r_squared"],
                    "signal_up_ratio": metrics["up_ratio"],
                    "signal_max_drawdown_pct": metrics["max_drawdown_pct"],
                })
    return trades


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return math.nan
    index = (len(values) - 1) * fraction
    lower, upper = math.floor(index), math.ceil(index)
    return values[lower] if lower == upper else values[lower] + (values[upper] - values[lower]) * (index - lower)


def summarize(trades, horizons):
    summary = []
    for horizon in horizons:
        rows = [row for row in trades if row["horizon"] == horizon]
        returns = [row["return_pct"] for row in rows]
        mfes = [row["mfe_pct"] for row in rows]
        maes = [row["mae_pct"] for row in rows]
        if not rows:
            continue
        summary.append({
            "horizon": horizon, "signals": len(rows),
            "win_rate_pct": sum(value > 0 for value in returns) / len(rows) * 100,
            "avg_return_pct": statistics.mean(returns),
            "median_return_pct": statistics.median(returns),
            "p25_return_pct": percentile(returns, 0.25),
            "p75_return_pct": percentile(returns, 0.75),
            "avg_mfe_pct": statistics.mean(mfes), "median_mfe_pct": statistics.median(mfes),
            "avg_mae_pct": statistics.mean(maes), "median_mae_pct": statistics.median(maes),
        })
    return summary


def write_csv(path, rows):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_backtest_to_db(args, horizons, trades, summary):
    conn = connect_db()
    run_id = str(uuid.uuid4())
    try:
        create_backtest_tables(conn)
        cursor = conn.cursor()
        end_date = args.end or max((row["signal_date"] for row in trades), default=args.start)
        cursor.execute("""INSERT INTO st_backtest_run
            (run_id,strategy,start_date,end_date,window_days,horizons,min_gain_pct,
             min_r_squared,min_up_ratio,max_drawdown_pct,status)
            VALUES(%s,'smooth_uptrend',%s,%s,%s,%s,%s,%s,%s,%s,'running')""",
            (run_id,args.start,end_date,args.window,','.join(map(str,horizons)),args.min_gain,
             args.min_r2,args.min_up_ratio,args.max_drawdown))
        trade_sql = """INSERT INTO st_backtest_trade
            (run_id,ts_code,signal_date,entry_date,entry_open,horizon,exit_date,exit_close,
             return_pct,mfe_pct,mae_pct,signal_gain_pct,signal_r_squared,signal_up_ratio,
             signal_max_drawdown_pct) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        values = [(run_id,row['ts_code'],row['signal_date'],row['entry_date'],row['entry_open'],
                   row['horizon'],row['exit_date'],row['exit_close'],row['return_pct'],
                   row['mfe_pct'],row['mae_pct'],row['signal_gain_pct'],row['signal_r_squared'],
                   row['signal_up_ratio'],row['signal_max_drawdown_pct']) for row in trades]
        for index in range(0, len(values), 1000):
            cursor.executemany(trade_sql, values[index:index + 1000])
            conn.commit()
        summary_sql = """INSERT INTO st_backtest_summary
            (run_id,period_type,period_value,horizon,signals,win_rate_pct,avg_return_pct,
             median_return_pct,p25_return_pct,p75_return_pct,avg_mfe_pct,median_mfe_pct,
             avg_mae_pct,median_mae_pct) VALUES(%s,'all','all',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        cursor.executemany(summary_sql, [(run_id,row['horizon'],row['signals'],row['win_rate_pct'],
            row['avg_return_pct'],row['median_return_pct'],row['p25_return_pct'],row['p75_return_pct'],
            row['avg_mfe_pct'],row['median_mfe_pct'],row['avg_mae_pct'],row['median_mae_pct']) for row in summary])
        cursor.execute("UPDATE st_backtest_run SET status='completed',trade_count=%s,completed_at=NOW() WHERE run_id=%s",
                       (len(trades),run_id))
        conn.commit()
        return run_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    args = parse_args()
    horizons = tuple(sorted({int(value) for value in args.horizons.split(",") if int(value) > 0}))
    if args.window < 2 or not horizons:
        raise ValueError("window 至少為 2，horizons 必須包含正整數")
    started = time.perf_counter()
    market = load_market_data(args, max(horizons))
    trades = run_backtest(market, args, horizons)
    summary = summarize(trades, horizons)
    write_csv(os.path.join(args.output_dir, "trades.csv"), trades)
    write_csv(os.path.join(args.output_dir, "summary.csv"), summary)
    run_id = None if args.no_db else save_backtest_to_db(args, horizons, trades, summary)
    print("無前視回測完成（訊號收盤後產生，下一交易日開盤進場）")
    print("注意：資料庫缺少歷史 ST／退市狀態，無法完全消除存活者偏差。")
    for row in summary:
        print(
            f"{row['horizon']:>2}日: {row['signals']} 筆 | 勝率 {row['win_rate_pct']:.2f}% | "
            f"平均 {row['avg_return_pct']:.2f}% | 中位 {row['median_return_pct']:.2f}% | "
            f"MFE中位 {row['median_mfe_pct']:.2f}% | MAE中位 {row['median_mae_pct']:.2f}%"
        )
    print(f"輸出: {args.output_dir} | 耗時 {time.perf_counter() - started:.2f} 秒")
    if run_id:
        print(f"資料庫回測批次: {run_id}")


if __name__ == "__main__":
    main()
