from __future__ import annotations

from collections.abc import Iterable
import warnings

import pandas as pd
import yfinance as yf

from app.models.schemas import UniverseStock


def fetch_price_history(stock: UniverseStock, period: str = "9mo", interval: str = "1d") -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*ChainedAssignmentError: behaviour will change in pandas 3\.0!.*",
            category=FutureWarning,
            module=r"yfinance\.(scrapers\.history|utils)",
        )
        history = yf.Ticker(stock.ticker).history(period=period, interval=interval, auto_adjust=False)
    if history.empty:
        raise ValueError(f"No market data for {stock.ticker}")
    history = history.reset_index()
    history.columns = [str(col).lower().replace(" ", "_") for col in history.columns]
    return history


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
