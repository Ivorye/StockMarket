"""質量代理＋中期動量＋趨勢確認的無前視偏差組合回測。

現有資料庫沒有歷史財務指標，因此「質量」使用價格/流動性代理：
低波動、低回撤、足夠成交額。訊號於收盤計算，下一交易日開盤成交。
"""

import argparse
import bisect
import csv
import math
import os
import statistics
from collections import defaultdict

import pymysql


def parse_args():
    p = argparse.ArgumentParser(description="質量代理＋中期動量＋趨勢確認回測")
    p.add_argument("--start", default="20240101", help="開始日期 YYYYMMDD")
    p.add_argument("--end", default="", help="結束日期；預設資料庫最新日")
    p.add_argument("--top", type=int, default=20, help="每期持股數")
    p.add_argument("--rebalance", type=int, default=20, help="調倉間隔（交易日）")
    p.add_argument("--momentum", type=int, default=120, help="動量回看期")
    p.add_argument("--skip", type=int, default=20, help="動量跳過最近交易日數")
    p.add_argument("--quality-window", type=int, default=60)
    p.add_argument("--max-vol", type=float, default=45, help="年化波動率上限(%)")
    p.add_argument("--max-drawdown", type=float, default=20, help="質量窗口最大回撤上限(%)")
    p.add_argument("--min-amount", type=float, default=50000, help="日均成交額下限（st_daily amount 單位）")
    p.add_argument("--cost", type=float, default=0.15, help="單邊交易成本(%)")
    p.add_argument("--output-dir", default="output/backtest_quality_momentum")
    return p.parse_args()


def connect_db():
    return pymysql.connect(host="localhost", user="root", password="P@ssw0rd",
                           database="stockshare", read_timeout=120)


def load_data(args):
    db = connect_db()
    try:
        c = db.cursor()
        c.execute("SELECT MAX(trade_date) FROM st_daily")
        end = args.end or c.fetchone()[0]
        c.execute("SELECT DISTINCT trade_date FROM st_daily WHERE trade_date<=%s ORDER BY trade_date", (end,))
        dates = [r[0] for r in c.fetchall()]
        start_pos = next((i for i, d in enumerate(dates) if d >= args.start), len(dates))
        warmup = max(args.momentum + args.skip, 120, args.quality_window) + 5
        query_start = dates[max(0, start_pos - warmup)]
        c.execute("""SELECT d.ts_code,d.trade_date,d.openp,d.closep,d.amount,
                            COALESCE(NULLIF(s.name,''),s.fullname,''),COALESCE(s.list_date,'')
                     FROM st_daily d LEFT JOIN stocks s ON s.st_code=d.ts_code
                     WHERE d.trade_date BETWEEN %s AND %s
                       AND d.openp>0 AND d.closep>0
                     ORDER BY d.ts_code,d.trade_date""", (query_start, end))
        series = defaultdict(list)
        names = {}
        for code, date, openp, closep, amount, name, list_date in c:
            series[code].append((date, float(openp), float(closep), float(amount or 0), list_date))
            names[code] = name
        return dates, series, names, end
    finally:
        db.close()


def max_drawdown(values):
    peak, worst = values[0], 0.0
    for value in values[1:]:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst * 100


def score_stock(rows, signal_date, args, row_dates=None):
    row_dates = row_dates or [row[0] for row in rows]
    end_index = bisect.bisect_right(row_dates, signal_date)
    needed = max(args.momentum + args.skip + 1, 121, args.quality_window + 1)
    if end_index < needed:
        return None
    eligible = rows[end_index - needed:end_index]
    closes = [r[2] for r in eligible]
    if args.skip:
        momentum = closes[-args.skip - 1] / closes[-args.momentum - args.skip - 1] - 1
    else:
        momentum = closes[-1] / closes[-args.momentum - 1] - 1
    quality = eligible[-args.quality_window:]
    returns = [math.log(quality[i][2] / quality[i - 1][2]) for i in range(1, len(quality))]
    volatility = statistics.stdev(returns) * math.sqrt(252) * 100
    drawdown = max_drawdown([r[2] for r in quality])
    avg_amount = statistics.mean(r[3] for r in quality)
    ma60 = statistics.mean(closes[-60:])
    ma120 = statistics.mean(closes[-120:])
    ma60_old = statistics.mean(closes[-80:-20])
    trend_ok = closes[-1] > ma60 > ma120 and ma60 > ma60_old
    if (momentum <= 0 or volatility > args.max_vol or drawdown < -args.max_drawdown
            or avg_amount < args.min_amount or not trend_ok):
        return None
    # 動量為主，低波動與低回撤作質量加分。
    score = momentum * 100 - volatility * 0.25 + drawdown * 0.15
    return {"score": score, "momentum_pct": momentum * 100,
            "volatility_pct": volatility, "drawdown_pct": drawdown,
            "avg_amount": avg_amount}


def next_row(rows, date):
    return next((row for row in rows if row[0] > date), None)


def run_backtest(dates, series, names, args):
    test_dates = [d for d in dates if d >= args.start and (not args.end or d <= args.end)]
    signal_dates = test_dates[::args.rebalance]
    row_maps = {code: {row[0]: row for row in rows} for code, rows in series.items()}
    row_dates = {code: [row[0] for row in rows] for code, rows in series.items()}
    date_pos = {date: index for index, date in enumerate(test_dates)}
    signal_for_entry = {test_dates[date_pos[date] + 1]: date for date in signal_dates
                        if date_pos[date] + 1 < len(test_dates)}
    cash, holdings, last_prices = 1.0, {}, {}
    nav_rows, rebalance_rows = [], []
    cost_rate = args.cost / 100
    benchmark_nav = 1.0
    selections = {}
    for signal_date in signal_dates:
        candidates = []
        for code, rows in series.items():
            if code.startswith(("688", "8", "4")):
                continue
            metric = score_stock(rows, signal_date, args, row_dates[code])
            if metric:
                candidates.append((code, metric))
        candidates.sort(key=lambda item: item[1]["score"], reverse=True)
        selections[signal_date] = candidates[:args.top]

    previous_nav = 1.0
    previous_day = None
    for day in test_dates:
        # 基准是每日等权收益指数；缺少当日行情的股票贡献 0，避免复牌累计收益挤入单日。
        benchmark_returns = []
        for code, rows in series.items():
            if code.startswith(("688", "8", "4")):
                continue
            row = row_maps[code].get(day)
            previous_row = row_maps[code].get(previous_day) if previous_day else None
            if row and previous_row:
                benchmark_returns.append(row[2] / previous_row[2] - 1)
            elif previous_day:
                benchmark_returns.append(0.0)
        if benchmark_returns:
            benchmark_nav *= 1 + statistics.mean(benchmark_returns)

        if day in signal_for_entry:
            signal_date = signal_for_entry[day]
            selected = selections[signal_date]
            selected_codes = {code for code, _ in selected}
            # 开盘先更新可交易持仓估值；停牌持仓保留，不能虚构成交。
            opening_value = cash
            for code, shares in holdings.items():
                row = row_maps[code].get(day)
                price = row[1] if row else last_prices.get(code, 0)
                opening_value += shares * price
            turnover_value = 0.0
            # 卖出不再入选且当日可交易的股票。
            for code in list(holdings):
                row = row_maps[code].get(day)
                if code not in selected_codes and row:
                    proceeds = holdings.pop(code) * row[1]
                    cash += proceeds
                    turnover_value += proceeds
            cash -= turnover_value * cost_rate
            frozen_value = sum(
                shares * last_prices.get(code, 0)
                for code, shares in holdings.items() if not row_maps[code].get(day)
            )
            tradable_selected = [(code, metric) for code, metric in selected if row_maps[code].get(day)]
            allocatable_value = max(0.0, opening_value - frozen_value - turnover_value * cost_rate)
            target_value = (allocatable_value / (len(tradable_selected) * (1 + cost_rate))
                            if tradable_selected else 0.0)
            # 对入选且可交易股票调至目标金额；保留停牌股票原份额。
            buy_turnover = 0.0
            for rank, (code, metric) in enumerate(tradable_selected, 1):
                row = row_maps[code].get(day)
                if not row:
                    continue
                current_value = holdings.get(code, 0.0) * row[1]
                trade_value = target_value - current_value
                holdings[code] = holdings.get(code, 0.0) + trade_value / row[1]
                cash -= trade_value
                buy_turnover += abs(trade_value)
                rebalance_rows.append({"signal_date": signal_date, "entry_date": day,
                    "rank": rank, "ts_code": code, "name": names.get(code, ""),
                    **{key: round(value, 4) for key, value in metric.items()}})
            cash -= buy_turnover * cost_rate

        portfolio_value = cash
        for code, shares in holdings.items():
            row = row_maps[code].get(day)
            if row:
                last_prices[code] = row[2]
            portfolio_value += shares * last_prices.get(code, 0)
        daily_return = portfolio_value / previous_nav - 1 if previous_nav else 0
        nav_rows.append({"trade_date": day, "nav": round(portfolio_value, 8),
                         "daily_return_pct": round(daily_return * 100, 6),
                         "benchmark_nav": round(benchmark_nav, 8),
                         "positions": len(holdings)})
        previous_nav = portfolio_value
        previous_day = day
    return nav_rows, rebalance_rows


def summarize(nav_rows):
    if not nav_rows:
        return {}
    nav = [r["nav"] for r in nav_rows]
    daily = [nav[i] / nav[i - 1] - 1 for i in range(1, len(nav))]
    years = len(daily) / 252
    total = nav[-1] - 1
    cagr = (nav[-1] ** (1 / years) - 1) if years > 0 and nav[-1] > 0 else 0
    vol = statistics.stdev(daily) * math.sqrt(252) if len(daily) > 1 else 0
    sharpe = statistics.mean(daily) / statistics.stdev(daily) * math.sqrt(252) if len(daily) > 1 and statistics.stdev(daily) else 0
    benchmark_total = nav_rows[-1]["benchmark_nav"] - 1
    return {"start_date": nav_rows[0]["trade_date"], "end_date": nav_rows[-1]["trade_date"],
            "total_return_pct": total * 100, "cagr_pct": cagr * 100,
            "annual_volatility_pct": vol * 100, "sharpe_0rf": sharpe,
            "max_drawdown_pct": max_drawdown(nav),
            "benchmark_return_pct": benchmark_total * 100,
            "excess_return_pct": (total - benchmark_total) * 100}


def write_csv(path, rows):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def main():
    args = parse_args()
    if args.top < 1 or args.rebalance < 1 or args.momentum < 2 or args.skip < 0:
        raise ValueError("top/rebalance 必須為正數，momentum>=2，skip>=0")
    dates, series, names, end = load_data(args)
    nav, rebalances = run_backtest(dates, series, names, args)
    summary = summarize(nav)
    write_csv(os.path.join(args.output_dir, "nav.csv"), nav)
    write_csv(os.path.join(args.output_dir, "rebalances.csv"), rebalances)
    write_csv(os.path.join(args.output_dir, "summary.csv"), [summary] if summary else [])
    print("回測完成：訊號日收盤計算，下一交易日開盤成交，報酬已扣調倉成本。")
    print("質量因子為低波動、低回撤、流動性代理；不是財務 ROE/負債率/現金流。")
    if summary:
        print("區間 {start_date}~{end_date} | 總報酬 {total_return_pct:.2f}% | CAGR {cagr_pct:.2f}% | "
              "最大回撤 {max_drawdown_pct:.2f}% | Sharpe {sharpe_0rf:.2f}".format(**summary))
    print(f"調倉選股 {len(rebalances)} 筆；輸出：{args.output_dir}")


if __name__ == "__main__":
    main()
