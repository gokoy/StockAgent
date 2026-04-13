from __future__ import annotations

from collections import OrderedDict
from io import StringIO

import pandas as pd
import requests

from app.config import AppConfig
from app.data.holdings import load_holding_stocks
from app.data.watchlist import load_watchlist
from app.models.schemas import UniverseStock


SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"


def load_universe(symbols: list[str]) -> list[UniverseStock]:
    return [UniverseStock(ticker=symbol, name=symbol) for symbol in symbols]


def resolve_scan_universe(config: AppConfig) -> list[UniverseStock]:
    stocks: list[UniverseStock] = []
    mode = config.universe_mode

    stocks.extend(load_holding_stocks(config.holdings_path))

    if mode in {"manual", "discovery", "discovery_plus_watchlist"}:
        us_symbols = resolve_us_discovery_symbols(config)
        stocks.extend(_build_market_universe(us_symbols, market="US", source=f"us_{config.us_universe_source}"))
        stocks.extend(_build_market_universe(config.kr_universe_symbols, market="KR", source="kr_discovery"))

    if config.include_watchlist and mode in {"watchlist", "discovery_plus_watchlist"}:
        state = load_watchlist(config.watchlist_path)
        for entry in state.entries:
            if not entry.active:
                continue
            stocks.append(
                UniverseStock(
                    ticker=entry.ticker,
                    name=entry.name,
                    market=entry.market,
                    source=entry.source,
                    in_watchlist=True,
                )
            )

    if mode == "watchlist" and not config.include_watchlist:
        return []
    return _dedupe_universe(stocks)


def resolve_us_discovery_symbols(config: AppConfig) -> list[str]:
    source = config.us_universe_source
    if source == "sp500":
        symbols = _fetch_sp500_symbols()
        return symbols or config.us_universe_symbols
    if source == "nasdaq100":
        symbols = _fetch_nasdaq100_symbols()
        return symbols or config.us_universe_symbols
    if source in {"sp500_plus_nasdaq100", "combined"}:
        symbols = _fetch_sp500_symbols() + _fetch_nasdaq100_symbols()
        return _dedupe_symbols(symbols) or config.us_universe_symbols
    return config.us_universe_symbols


def _fetch_sp500_symbols() -> list[str]:
    try:
        html = requests.get(SP500_URL, timeout=15).text
        tables = pd.read_html(StringIO(html))
        if not tables:
            return []
        frame = tables[0]
        if "Symbol" not in frame.columns:
            return []
        return [_normalize_us_symbol(str(symbol)) for symbol in frame["Symbol"].dropna().tolist()]
    except Exception:
        return []


def _fetch_nasdaq100_symbols() -> list[str]:
    try:
        html = requests.get(NASDAQ100_URL, timeout=15).text
        tables = pd.read_html(StringIO(html))
        for frame in tables:
            columns = {str(col).strip() for col in frame.columns}
            if "Ticker" in columns:
                return [_normalize_us_symbol(str(symbol)) for symbol in frame["Ticker"].dropna().tolist()]
        return []
    except Exception:
        return []


def _normalize_us_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return normalized.replace(".", "-")


def _dedupe_symbols(symbols: list[str]) -> list[str]:
    seen: OrderedDict[str, None] = OrderedDict()
    for symbol in symbols:
        if symbol:
            seen[symbol] = None
    return list(seen.keys())


def _build_market_universe(symbols: list[str], market: str, source: str) -> list[UniverseStock]:
    return [UniverseStock(ticker=symbol, name=symbol, market=market, source=source) for symbol in symbols]


def _dedupe_universe(stocks: list[UniverseStock]) -> list[UniverseStock]:
    deduped: OrderedDict[str, UniverseStock] = OrderedDict()
    for stock in stocks:
        key = stock.ticker.upper()
        if key not in deduped:
            deduped[key] = stock
            continue
        existing = deduped[key]
        if stock.in_holdings and not existing.in_holdings:
            deduped[key] = stock
            continue
        if stock.in_watchlist and not existing.in_watchlist and not existing.in_holdings:
            deduped[key] = stock
    return list(deduped.values())
