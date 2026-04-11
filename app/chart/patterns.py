from __future__ import annotations

import pandas as pd


def is_volatility_contracting(history: pd.DataFrame) -> bool:
    recent_range = ((history["high"] - history["low"]) / history["close"]).tail(10).mean()
    prior_range = ((history["high"] - history["low"]) / history["close"]).tail(30).head(20).mean()
    return bool(recent_range < prior_range)


def is_breakout_setup(history: pd.DataFrame, distance_from_20d_high_pct: float, volume_ratio_20d: float) -> bool:
    close = float(history["close"].iloc[-1])
    ma20 = float(history["close"].rolling(window=20).mean().iloc[-1])
    return close > ma20 and distance_from_20d_high_pct >= -3.0 and volume_ratio_20d >= 1.0


def is_pullback_setup(history: pd.DataFrame, ma20: float, ma60: float) -> bool:
    close = float(history["close"].iloc[-1])
    return ma20 >= ma60 and close >= ma20 * 0.98 and close <= ma20 * 1.03


def is_range_bound(history: pd.DataFrame) -> bool:
    high_30 = float(history["high"].tail(30).max())
    low_30 = float(history["low"].tail(30).min())
    close = float(history["close"].iloc[-1])
    width_pct = ((high_30 - low_30) / close) * 100 if close else 0.0
    return width_pct <= 12.0


def support_level_hint(history: pd.DataFrame, ma20: float, ma60: float) -> str:
    recent_low = float(history["low"].tail(20).min())
    return f"최근 20일 저점 {recent_low:.2f}, MA20 {ma20:.2f}, MA60 {ma60:.2f}"
