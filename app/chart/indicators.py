from __future__ import annotations

import pandas as pd


def moving_average(series: pd.Series, window: int) -> float:
    return float(series.rolling(window=window).mean().iloc[-1])


def true_range(history: pd.DataFrame) -> pd.Series:
    prev_close = history["close"].shift(1)
    ranges = pd.concat(
        [
            history["high"] - history["low"],
            (history["high"] - prev_close).abs(),
            (history["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr_pct(history: pd.DataFrame, window: int = 14) -> float:
    atr = true_range(history).rolling(window=window).mean().iloc[-1]
    close = float(history["close"].iloc[-1])
    return float(atr / close * 100) if close else 0.0
