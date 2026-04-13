from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import HoldingInput, HoldingsInput, UniverseStock


def load_holdings(path: Path) -> HoldingsInput:
    if not path.exists():
        return HoldingsInput()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return HoldingsInput.model_validate(payload)


def load_holding_stocks(path: Path) -> list[UniverseStock]:
    holdings = load_holdings(path)
    stocks: list[UniverseStock] = []
    for item in holdings.kr:
        stocks.append(_to_universe_stock(item, default_market="KR"))
    for item in holdings.us:
        stocks.append(_to_universe_stock(item, default_market="US"))
    return stocks


def count_holdings(path: Path) -> dict[str, int]:
    holdings = load_holdings(path)
    return {
        "kr": len(holdings.kr),
        "us": len(holdings.us),
        "total": len(holdings.kr) + len(holdings.us),
    }


def _to_universe_stock(item: HoldingInput, default_market: str) -> UniverseStock:
    market = (item.market or default_market).upper()
    return UniverseStock(
        ticker=item.ticker.upper(),
        name=item.ticker.upper(),
        market=market,
        source="holding",
        in_holdings=True,
    )
