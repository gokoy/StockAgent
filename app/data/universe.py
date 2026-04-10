from __future__ import annotations

from app.models.schemas import UniverseStock


def load_universe(symbols: list[str]) -> list[UniverseStock]:
    return [UniverseStock(ticker=symbol, name=symbol) for symbol in symbols]
