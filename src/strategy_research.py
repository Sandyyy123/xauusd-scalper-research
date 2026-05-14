"""
XAUUSD Scalping Strategy — Signal Research Pipeline
Author: Dr. Sandeep Grover
"""

import argparse
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time


# ── Indicator computations ────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 7) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k_period: int = 5, d_period: int = 3) -> tuple[pd.Series, pd.Series]:
    low_min = low.rolling(k_period).min()
    high_max = high.rolling(k_period).max()
    k = 100 * (close - low_min) / (high_max - low_min + 1e-10)
    d = k.rolling(d_period).mean()
    return k, d


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── Session filter ────────────────────────────────────────────────────────────

TRADE_SESSIONS = [
    (time(7, 0), time(11, 0)),   # London open
    (time(13, 0), time(17, 0)),  # London-NY overlap (highest profitability)
]


def in_trade_session(ts: pd.Timestamp) -> bool:
    t = ts.time()
    return any(start <= t <= end for start, end in TRADE_SESSIONS)


# ── Signal generation ─────────────────────────────────────────────────────────

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Three-layer signal architecture:
    1. Trend filter   — EMA 20/50 crossover (trade only in trend direction)
    2. Entry trigger  — RSI(7) divergence + Stochastic(5,3,3) oversold/overbought
    3. Volatility gate — ATR threshold + session filter
    """
    df = df.copy()

    # Layer 1: trend
    df["ema20"] = ema(df["Close"], 20)
    df["ema50"] = ema(df["Close"], 50)
    df["trend_up"]   = df["ema20"] > df["ema50"]
    df["trend_down"] = df["ema20"] < df["ema50"]

    # Layer 2: entry trigger
    df["rsi"] = rsi(df["Close"], 7)
    df["stoch_k"], df["stoch_d"] = stochastic(df["High"], df["Low"], df["Close"])

    # Oversold / overbought thresholds
    rsi_low, rsi_high   = 30, 70
    stoch_low, stoch_high = 20, 80

    long_trigger  = (df["rsi"] < rsi_low)  & (df["stoch_k"] < stoch_low)  & (df["stoch_k"] > df["stoch_d"])
    short_trigger = (df["rsi"] > rsi_high) & (df["stoch_k"] > stoch_high) & (df["stoch_k"] < df["stoch_d"])

    # Layer 3: volatility gate
    df["atr"] = atr(df["High"], df["Low"], df["Close"])
    atr_threshold = df["atr"].rolling(50).mean() * 0.8   # require meaningful vol
    vol_ok = df["atr"] > atr_threshold

    # Session filter
    df["session_ok"] = df.index.map(in_trade_session)

    # Final signals
    df["signal_long"]  = df["trend_up"]   & long_trigger  & vol_ok & df["session_ok"]
    df["signal_short"] = df["trend_down"] & short_trigger & vol_ok & df["session_ok"]

    return df


# ── Entry / exit logic ────────────────────────────────────────────────────────

def compute_entries(df: pd.DataFrame, atr_sl_mult: float = 1.0, atr_tp_mult: float = 1.5) -> pd.DataFrame:
    """
    SL = entry ± atr_sl_mult * ATR
    TP = entry ± atr_tp_mult * ATR   (R:R = 1:1.5 for positive expectancy at 75% WR)
    """
    df = df.copy()
    df["sl_long"]  = df["Close"] - atr_sl_mult * df["atr"]
    df["tp_long"]  = df["Close"] + atr_tp_mult * df["atr"]
    df["sl_short"] = df["Close"] + atr_sl_mult * df["atr"]
    df["tp_short"] = df["Close"] - atr_tp_mult * df["atr"]
    return df


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="XAUUSD Scalping Research")
    parser.add_argument("--symbol",    default="GC=F",       help="Yahoo Finance symbol")
    parser.add_argument("--timeframe", default="5m",         help="Bar interval")
    parser.add_argument("--start",     default="2023-01-01", help="Start date")
    parser.add_argument("--end",       default="2024-04-30", help="End date")
    args = parser.parse_args()

    print(f"Fetching {args.symbol} {args.timeframe} data from {args.start} to {args.end}...")
    raw = yf.download(args.symbol, start=args.start, end=args.end, interval=args.timeframe, progress=False)

    if raw.empty:
        print("No data returned. Check symbol / date range.")
        return

    df = generate_signals(raw)
    df = compute_entries(df)

    n_long  = df["signal_long"].sum()
    n_short = df["signal_short"].sum()
    print(f"Signals generated — Long: {n_long}, Short: {n_short}")
    print("Running backtest... use backtester.py for full walk-forward results.")


if __name__ == "__main__":
    main()
