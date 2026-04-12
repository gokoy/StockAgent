from __future__ import annotations

from collections.abc import Iterable
import warnings

import pandas as pd
import yfinance as yf

from app.models.schemas import UniverseStock


def fetch_price_history(stock: UniverseStock, period: str = "9mo", interval: str = "1d") -> pd.DataFrame:
    return fetch_symbol_history(stock.ticker, period=period, interval=interval)


def fetch_symbol_history(symbol: str, period: str = "9mo", interval: str = "1d") -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*ChainedAssignmentError: behaviour will change in pandas 3\.0!.*",
            category=FutureWarning,
            module=r"yfinance\.(scrapers\.history|utils)",
        )
        history = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    if history.empty:
        raise ValueError(f"No market data for {symbol}")
    history = history.reset_index()
    history.columns = [str(col).lower().replace(" ", "_") for col in history.columns]
    return history


def fetch_latest_close_change(symbol: str, period: str = "10d") -> tuple[float, float]:
    history = fetch_symbol_history(symbol, period=period, interval="1d")
    close = history["close"].dropna()
    if close.empty:
        raise ValueError(f"No close data for {symbol}")
    latest = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) >= 2 else latest
    change_pct = ((latest / prev) - 1.0) * 100 if prev else 0.0
    return latest, change_pct


def fetch_trailing_return(symbol: str, period: str = "2mo", lookback_days: int = 5) -> float:
    history = fetch_symbol_history(symbol, period=period, interval="1d")
    close = history["close"].dropna()
    if len(close) <= lookback_days:
        return 0.0
    latest = float(close.iloc[-1])
    base = float(close.iloc[-(lookback_days + 1)])
    return ((latest / base) - 1.0) * 100 if base else 0.0


def fetch_company_names(stocks: Iterable[UniverseStock]) -> dict[str, str]:
    names: dict[str, str] = {}
    for stock in stocks:
        try:
            ticker = yf.Ticker(stock.ticker)
            short_name = ""
            info = getattr(ticker, "info", {}) or {}
            if isinstance(info, dict):
                short_name = str(info.get("shortName") or info.get("longName") or "").strip()
            names[stock.ticker] = short_name or stock.name
        except Exception:
            names[stock.ticker] = stock.name
    return names
