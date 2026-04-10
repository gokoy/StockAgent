from __future__ import annotations

import pandas as pd


def passes_price_filter(history: pd.DataFrame, min_price: float) -> bool:
    return float(history["close"].iloc[-1]) >= min_price


def passes_volume_filter(history: pd.DataFrame, min_avg_volume: int) -> bool:
    avg_volume = float(history["volume"].tail(20).mean())
    return avg_volume >= min_avg_volume


def has_sufficient_history(history: pd.DataFrame, min_rows: int = 140) -> bool:
    return len(history) >= min_rows
