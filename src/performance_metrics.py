"""
Performance Metrics — Win Rate, Drawdown, Sharpe, Return/DD Ratio
Author: Dr. Sandeep Grover
"""

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backtester import TradeRecord


def compute_metrics(trades: list) -> dict:
    """
    Compute all key performance metrics from a list of TradeRecord objects.
    Returns a flat dict suitable for DataFrame rows.
    """
    if not trades:
        return {}

    pnls   = [t.pnl_pct for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    durations = [t.duration_min for t in trades if t.duration_min > 0]

    win_rate  = len(wins) / len(pnls) if pnls else 0.0
    avg_win   = np.mean(wins)   if wins   else 0.0
    avg_loss  = np.mean(losses) if losses else 0.0

    # Profit factor
    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf

    # Expectancy per trade
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    # Equity curve + drawdown
    equity = np.cumsum(pnls)
    running_max = np.maximum.accumulate(equity)
    drawdown    = equity - running_max
    max_dd      = abs(drawdown.min()) if len(drawdown) > 0 else 0.0

    # Monthly return (assuming 22 trading days of 5m bars)
    total_return = equity[-1] if len(equity) > 0 else 0.0
    n_months     = max(len(trades) / 22, 1)
    monthly_return = total_return / n_months

    # Return / max drawdown ratio (client target: 4-5x)
    return_dd_ratio = monthly_return / max_dd if max_dd > 0 else np.inf

    # Sharpe (annualised, 252 trading days)
    pnl_series = np.array(pnls)
    sharpe = (pnl_series.mean() / (pnl_series.std() + 1e-10)) * np.sqrt(252 * 78)  # 78 bars/day at M5

    return {
        "n_trades":         len(trades),
        "win_rate":         round(win_rate * 100, 2),
        "profit_factor":    round(profit_factor, 3),
        "expectancy":       round(expectancy * 100, 4),
        "avg_win_pct":      round(avg_win * 100, 4),
        "avg_loss_pct":     round(avg_loss * 100, 4),
        "max_drawdown_pct": round(max_dd * 100, 4),
        "monthly_return_pct": round(monthly_return * 100, 4),
        "return_dd_ratio":  round(return_dd_ratio, 3),
        "sharpe":           round(sharpe, 3),
        "avg_duration_min": round(np.mean(durations), 1) if durations else 0.0,
    }


def print_report(metrics: dict) -> None:
    print("\n" + "=" * 50)
    print("  BACKTEST PERFORMANCE REPORT")
    print("=" * 50)
    for k, v in metrics.items():
        label = k.replace("_", " ").title()
        print(f"  {label:<28} {v}")
    print("=" * 50)
    # Highlight against client targets
    wr  = metrics.get("win_rate", 0)
    rdd = metrics.get("return_dd_ratio", 0)
    print(f"\n  Target: Win Rate >= 75%     {'PASS' if wr  >= 75 else 'FAIL'} ({wr}%)")
    print(f"  Target: Return/DD >= 4x     {'PASS' if rdd >= 4  else 'FAIL'} ({rdd}x)")
    print()
