from __future__ import annotations

from collections import OrderedDict

from app.config import AppConfig
from app.data.watchlist import load_watchlist
from app.models.schemas import UniverseStock


def load_universe(symbols: list[str]) -> list[UniverseStock]:
    return [UniverseStock(ticker=symbol, name=symbol) for symbol in symbols]


def resolve_scan_universe(config: AppConfig) -> list[UniverseStock]:
    stocks: list[UniverseStock] = []
    mode = config.universe_mode

    if mode in {"manual", "discovery", "discovery_plus_watchlist"}:
        stocks.extend(_build_market_universe(config.us_universe_symbols, market="US", source="us_discovery"))
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
        if stock.in_watchlist and not existing.in_watchlist:
            deduped[key] = stock
    return list(deduped.values())
