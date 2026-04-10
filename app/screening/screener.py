from __future__ import annotations

import pandas as pd

from app.screening.filters import has_sufficient_history, passes_price_filter, passes_volume_filter


def screen_stock(history: pd.DataFrame, min_price: float, min_avg_volume: int) -> tuple[bool, str]:
    if not has_sufficient_history(history):
        return False, "insufficient_history"
    if not passes_price_filter(history, min_price):
        return False, "price_below_threshold"
    if not passes_volume_filter(history, min_avg_volume):
        return False, "volume_below_threshold"
    return True, "passed"
