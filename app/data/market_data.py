from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
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


def fetch_upcoming_earnings_date(symbol: str) -> str | None:
    try:
        ticker = yf.Ticker(symbol)
        calendar = getattr(ticker, "calendar", None)
        if calendar is None:
            return None
        if hasattr(calendar, "empty") and calendar.empty:
            return None

        value = None
        if hasattr(calendar, "index") and "Earnings Date" in getattr(calendar, "index", []):
            raw = calendar.loc["Earnings Date"]
            if hasattr(raw, "iloc"):
                value = raw.iloc[0]
            else:
                value = raw
        elif isinstance(calendar, dict):
            value = calendar.get("Earnings Date")

        if value is None:
            return None
        if isinstance(value, (list, tuple)) and value:
            value = value[0]
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        value_str = str(value).strip()
        return value_str[:10] if value_str else None
    except Exception:
        return None


def fetch_forward_return(symbol: str, start_date: str, trading_days: int) -> float | None:
    stats = fetch_forward_path_stats(symbol, start_date, trading_days)
    return stats.get(f"return_{trading_days}d")


def fetch_forward_path_stats(symbol: str, start_date: str, trading_days: int) -> dict[str, float | None]:
    try:
        history = fetch_symbol_history(symbol, period="18mo", interval="1d").copy()
        history = history.dropna(subset=["date", "close"]).reset_index(drop=True)
        date_only = pd.to_datetime(history["date"]).dt.strftime("%Y-%m-%d")
        matches = history.index[date_only >= start_date].tolist()
        if not matches:
            return _empty_forward_stats(trading_days)
        start_idx = matches[0]
        end_idx = start_idx + trading_days
        if end_idx >= len(history):
            return _empty_forward_stats(trading_days)
        start_close = float(history.loc[start_idx, "close"])
        if not start_close:
            return _empty_forward_stats(trading_days)
        window = history.loc[start_idx:end_idx].copy()
        closes = window["close"].dropna().astype(float)
        if closes.empty:
            return _empty_forward_stats(trading_days)
        end_close = float(closes.iloc[-1])
        max_close = float(closes.max())
        min_close = float(closes.min())
        return {
            f"return_{trading_days}d": ((end_close / start_close) - 1.0) * 100,
            f"max_upside_{trading_days}d": ((max_close / start_close) - 1.0) * 100,
            f"max_drawdown_{trading_days}d": ((min_close / start_close) - 1.0) * 100,
        }
    except Exception:
        return _empty_forward_stats(trading_days)


def fetch_forward_close_path(symbol: str, start_date: str, trading_days: int) -> list[float]:
    try:
        history = fetch_symbol_history(symbol, period="18mo", interval="1d").copy()
        history = history.dropna(subset=["date", "close"]).reset_index(drop=True)
        date_only = pd.to_datetime(history["date"]).dt.strftime("%Y-%m-%d")
        matches = history.index[date_only >= start_date].tolist()
        if not matches:
            return []
        start_idx = matches[0]
        end_idx = min(start_idx + trading_days, len(history) - 1)
        closes = history.loc[start_idx:end_idx, "close"].dropna().astype(float).tolist()
        return closes
    except Exception:
        return []


def _empty_forward_stats(trading_days: int) -> dict[str, float | None]:
    return {
        f"return_{trading_days}d": None,
        f"max_upside_{trading_days}d": None,
        f"max_drawdown_{trading_days}d": None,
    }
