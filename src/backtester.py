"""
Walk-Forward Backtesting Engine — XAUUSD Scalping
Author: Dr. Sandeep Grover
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Literal

from strategy_research import generate_signals, compute_entries
from performance_metrics import compute_metrics


@dataclass
class TradeRecord:
    direction: Literal["long", "short"]
    entry_price: float
    sl: float
    tp: float
    entry_time: pd.Timestamp
    exit_price: float = 0.0
    exit_time: pd.Timestamp = None
    outcome: Literal["tp", "sl", "open"] = "open"
    pnl_pct: float = 0.0
    duration_min: float = 0.0


@dataclass
class BacktestConfig:
    sl_mult: float = 1.0
    tp_mult: float = 1.5
    max_concurrent: int = 2
    commission_per_trade: float = 0.0003   # 3 pips round-trip on Gold
    slippage: float = 0.0001


def simulate_trade(row: pd.Series, direction: str, future: pd.DataFrame,
                   config: BacktestConfig) -> TradeRecord:
    """Simulate a single trade using future bars for exit simulation."""
    entry = row["Close"] * (1 + config.slippage if direction == "long" else 1 - config.slippage)
    sl = row[f"sl_{direction}"]
    tp = row[f"tp_{direction}"]

    rec = TradeRecord(
        direction=direction,
        entry_price=entry,
        sl=sl,
        tp=tp,
        entry_time=row.name,
    )

    for _, bar in future.iterrows():
        if direction == "long":
            if bar["Low"] <= sl:
                rec.exit_price = sl
                rec.outcome = "sl"
                break
            if bar["High"] >= tp:
                rec.exit_price = tp
                rec.outcome = "tp"
                break
        else:
            if bar["High"] >= sl:
                rec.exit_price = sl
                rec.outcome = "sl"
                break
            if bar["Low"] <= tp:
                rec.exit_price = tp
                rec.outcome = "tp"
                break
        rec.exit_time = bar.name

    if rec.outcome == "open":
        rec.exit_price = future.iloc[-1]["Close"]
        rec.exit_time  = future.index[-1]

    sign = 1 if direction == "long" else -1
    rec.pnl_pct = sign * (rec.exit_price - entry) / entry - config.commission_per_trade
    if rec.exit_time:
        rec.duration_min = (rec.exit_time - rec.entry_time).total_seconds() / 60

    return rec


def run_backtest(df: pd.DataFrame, config: BacktestConfig = BacktestConfig()) -> list[TradeRecord]:
    df = generate_signals(df)
    df = compute_entries(df, config.sl_mult, config.tp_mult)

    trades: list[TradeRecord] = []
    open_count = 0

    for i, (ts, row) in enumerate(df.iterrows()):
        if open_count >= config.max_concurrent:
            # Release closed trades
            open_count = sum(1 for t in trades if t.outcome == "open")

        future = df.iloc[i + 1: i + 1 + 60]  # up to 60 bars (~5h at M5)
        if future.empty:
            break

        if row["signal_long"] and open_count < config.max_concurrent:
            trades.append(simulate_trade(row, "long", future, config))
            open_count += 1

        elif row["signal_short"] and open_count < config.max_concurrent:
            trades.append(simulate_trade(row, "short", future, config))
            open_count += 1

    return trades


def walk_forward(df: pd.DataFrame, train_months: int = 6, test_months: int = 2) -> pd.DataFrame:
    """
    Roll a train/test window across the full dataset.
    Optimizes SL/TP multipliers on train, evaluates on out-of-sample test.
    """
    results = []
    df.index = pd.to_datetime(df.index)
    start = df.index.min()
    end   = df.index.max()

    window_start = start
    fold = 0

    while True:
        train_end = window_start + pd.DateOffset(months=train_months)
        test_end  = train_end   + pd.DateOffset(months=test_months)
        if test_end > end:
            break

        train_df = df[window_start:train_end]
        test_df  = df[train_end:test_end]

        # Simple grid search over multipliers on train
        best_config = BacktestConfig()
        best_sharpe = -np.inf
        for sl in [0.8, 1.0, 1.2]:
            for tp in [1.2, 1.5, 1.8]:
                cfg = BacktestConfig(sl_mult=sl, tp_mult=tp)
                t_trades = run_backtest(train_df, cfg)
                if not t_trades:
                    continue
                m = compute_metrics(t_trades)
                if m["sharpe"] > best_sharpe:
                    best_sharpe = m["sharpe"]
                    best_config = cfg

        # Evaluate on out-of-sample
        oos_trades = run_backtest(test_df, best_config)
        if oos_trades:
            m = compute_metrics(oos_trades)
            m.update({
                "fold": fold,
                "test_start": str(train_end.date()),
                "test_end":   str(test_end.date()),
                "sl_mult":    best_config.sl_mult,
                "tp_mult":    best_config.tp_mult,
            })
            results.append(m)

        window_start += pd.DateOffset(months=test_months)
        fold += 1

    return pd.DataFrame(results)


if __name__ == "__main__":
    import yfinance as yf
    raw = yf.download("GC=F", start="2023-01-01", end="2024-04-30", interval="5m", progress=False)
    summary = walk_forward(raw)
    print(summary.to_string(index=False))
    summary.to_csv("../outputs/backtest_report.csv", index=False)
    print("Saved → outputs/backtest_report.csv")
