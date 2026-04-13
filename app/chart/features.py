from __future__ import annotations

import pandas as pd

from app.chart.indicators import atr_pct, moving_average
from app.chart.patterns import (
    is_breakout_setup,
    is_pullback_setup,
    is_range_bound,
    is_volatility_contracting,
    support_level_hint,
)
from app.models.schemas import ChartFeatures


def build_chart_features(history: pd.DataFrame) -> ChartFeatures:
    history = history.dropna(subset=["close", "high", "low", "volume"]).reset_index(drop=True)
    close = history["close"]
    last_close = float(close.iloc[-1])
    ma20 = moving_average(close, 20)
    ma60 = moving_average(close, 60)
    ma120 = moving_average(close, 120)
    high_20 = float(history["high"].tail(20).max())
    high_60 = float(history["high"].tail(60).max())
    avg_volume_20 = float(history["volume"].tail(20).mean())
    latest_volume = float(history["volume"].iloc[-1])
    volume_ratio = latest_volume / avg_volume_20 if avg_volume_20 else 0.0
    distance_from_20d_high_pct = ((last_close / high_20) - 1.0) * 100 if high_20 else 0.0
    distance_from_60d_high_pct = ((last_close / high_60) - 1.0) * 100 if high_60 else 0.0
    overextended_pct = ((last_close / ma20) - 1.0) * 100 if ma20 else 0.0
    recent_sharp_runup = bool((last_close / float(close.tail(15).iloc[0]) - 1.0) * 100 >= 15.0)
    volatility_contracting = is_volatility_contracting(history)
    breakout_setup = is_breakout_setup(history, distance_from_20d_high_pct, volume_ratio)
    pullback_setup = is_pullback_setup(history, ma20, ma60)
    range_bound = is_range_bound(history)
    return ChartFeatures(
        ma20=round(ma20, 4),
        ma60=round(ma60, 4),
        ma120=round(ma120, 4),
        above_ma20=last_close >= ma20,
        above_ma60=last_close >= ma60,
        above_ma120=last_close >= ma120,
        distance_from_20d_high_pct=round(distance_from_20d_high_pct, 4),
        distance_from_60d_high_pct=round(distance_from_60d_high_pct, 4),
        volume_ratio_20d=round(volume_ratio, 4),
        atr_pct=round(atr_pct(history), 4),
        volatility_contracting=volatility_contracting,
        breakout_setup=breakout_setup,
        pullback_setup=pullback_setup,
        range_bound=range_bound,
        overextended_pct=round(overextended_pct, 4),
        recent_sharp_runup=recent_sharp_runup,
        support_level_hint=support_level_hint(history, ma20, ma60),
    )
