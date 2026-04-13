from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.data.holdings import load_holding_stocks
from app.data.market_data import fetch_company_names, fetch_upcoming_earnings_date
from app.data.news_data import fetch_market_event_news
from app.data.universe import resolve_us_discovery_symbols


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update structured market event calendar snapshot")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--max-news-age-hours", type=int, default=120, help="Lookback window for event news")
    parser.add_argument("--universe-limit", type=int, default=8, help="How many discovery symbols to inspect for earnings")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config()
    output_path = Path(args.output or str(config.event_calendar_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "KR": _build_market_payload("KR", args.max_news_age_hours, args.universe_limit),
        "US": _build_market_payload("US", args.max_news_age_hours, args.universe_limit),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"event_calendar_written path={output_path}")
    return 0


def _build_market_payload(market: str, max_news_age_hours: int, universe_limit: int) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for event in fetch_market_event_news(market, max_age_hours=max_news_age_hours, limit=8):
        date_label = event.published_at.strftime("%Y-%m-%d")
        title = _normalize_event_title(event.headline)
        key = (date_label, title)
        if key in seen or not title:
            continue
        seen.add(key)
        items.append(
            {
                "date": date_label,
                "title": title,
                "category": "macro",
                "importance": "high",
                "source": event.source or "google_news",
            }
        )

    symbols = _symbols_for_market(market, universe_limit)
    names = fetch_company_names(symbols)
    for stock in symbols:
        earnings_date = fetch_upcoming_earnings_date(stock.ticker)
        if not earnings_date:
            continue
        title = f"{names.get(stock.ticker, stock.ticker)} 실적 발표 예정"
        key = (earnings_date, title)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "date": earnings_date,
                "title": title,
                "category": "earnings",
                "importance": "medium" if stock.in_holdings else "low",
                "ticker": stock.ticker,
                "source": "yfinance",
            }
        )

    items.sort(key=lambda item: (item.get("date", ""), 0 if item.get("importance") == "high" else 1, item.get("title", "")))
    return items[:20]


def _symbols_for_market(market: str, universe_limit: int):
    config = load_config()
    holdings = [stock for stock in load_holding_stocks(config.holdings_path) if stock.market == market]
    if market == "US":
        discovery = resolve_us_discovery_symbols(config)[:universe_limit]
    else:
        discovery = config.kr_universe_symbols[:universe_limit]
    seen = {stock.ticker for stock in holdings}
    for ticker in discovery:
        if ticker in seen:
            continue
        from app.models.schemas import UniverseStock

        holdings.append(UniverseStock(ticker=ticker, name=ticker, market=market, source="calendar"))
        seen.add(ticker)
    return holdings


def _normalize_event_title(headline: str) -> str:
    normalized = " ".join(headline.split()).strip(" -")
    replacements = (
        ("CPI", "미국 CPI 관련 이벤트"),
        ("PPI", "미국 PPI 관련 이벤트"),
        ("FOMC", "FOMC 관련 이벤트"),
        ("payroll", "미국 고용지표 관련 이벤트"),
        ("earnings", "실적 발표 관련 이벤트"),
        ("Treasury", "미국 국채금리 관련 이벤트"),
        ("economic calendar", "주요 경제 일정 브리핑"),
        ("경제 일정", "주요 경제 일정 브리핑"),
        ("환율", "환율 관련 이벤트"),
        ("한국은행", "한국은행 관련 이벤트"),
    )
    lowered = normalized.lower()
    for key, label in replacements:
        if key.lower() in lowered:
            return label
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
