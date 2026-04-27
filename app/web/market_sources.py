from __future__ import annotations

from functools import lru_cache
import warnings

import pandas as pd
import yfinance as yf


REQUIRED_HISTORY_COLUMNS = ("date", "open", "high", "low", "close", "volume")

KR_SECTOR_SYMBOLS: dict[str, list[str]] = {
    "반도체": ["005930.KS", "000660.KS"],
    "자동차": ["005380.KS", "000270.KS"],
    "인터넷": ["035420.KS", "035720.KS"],
    "2차전지": ["051910.KS", "006400.KS", "373220.KS"],
    "바이오": ["068270.KS", "207940.KS"],
    "방산": ["012450.KS", "079550.KS"],
    "전력기기": ["010120.KS", "267260.KS"],
}


@lru_cache(maxsize=256)
def fetch_symbol_history(symbol: str, period: str = "1y", interval: str = "1d", min_rows: int = 2) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        history = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    if history.empty:
        raise ValueError(f"No market data for {symbol}")
    history = history.reset_index()
    history.columns = [str(col).lower().replace(" ", "_") for col in history.columns]
    return _normalize_history(history, symbol=symbol, min_rows=min_rows)


def _normalize_history(history: pd.DataFrame, symbol: str, min_rows: int) -> pd.DataFrame:
    frame = history.copy()
    missing = [column for column in REQUIRED_HISTORY_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing columns for {symbol}: {', '.join(missing)}")

    frame = frame.loc[:, list(dict.fromkeys(frame.columns))].copy()
    frame["date"] = pd.to_datetime(frame["date"].astype(str).str[:10], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=numeric_columns).reset_index(drop=True)

    if len(frame) < min_rows:
        raise ValueError(f"Insufficient history for {symbol}: {len(frame)} < {min_rows}")
    if bool(((frame["close"] <= 0) | (frame["high"] < frame["low"])).any()):
        raise ValueError(f"Invalid OHLC rows for {symbol}")
    return frame
