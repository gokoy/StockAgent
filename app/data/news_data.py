from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser

from app.models.schemas import NewsItem


def fetch_latest_news(ticker: str, name: str, max_age_hours: int, limit: int = 5) -> list[NewsItem]:
    query = f"{ticker} stock"
    return fetch_news_by_query(query=query, max_age_hours=max_age_hours, limit=limit, hl="en-US", gl="US", ceid="US:en")


def fetch_news_by_query(
    query: str,
    max_age_hours: int,
    limit: int = 5,
    hl: str = "en-US",
    gl: str = "US",
    ceid: str = "US:en",
) -> list[NewsItem]:
    encoded_query = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl={hl}&gl={gl}&ceid={ceid}"
    feed = feedparser.parse(url)
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=max_age_hours)
    items: list[NewsItem] = []
    for entry in feed.entries:
        published_raw = entry.get("published")
        if not published_raw:
            continue
        published_at = parsedate_to_datetime(published_raw)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        published_at = published_at.astimezone(UTC)
        if published_at < cutoff:
            continue
        source = ""
        if entry.get("source") and isinstance(entry["source"], dict):
            source = entry["source"].get("title", "")
        summary = entry.get("summary", "").replace("<b>", "").replace("</b>", "")
        items.append(
            NewsItem(
                headline=entry.get("title", ""),
                summary=summary[:400],
                published_at=published_at,
                source=source,
                url=entry.get("link", ""),
            )
        )
        if len(items) >= limit:
            break
    return items


def fetch_market_news(market: str, max_age_hours: int, limit: int = 5) -> list[NewsItem]:
    normalized = market.upper()
    if normalized == "KR":
        return fetch_news_by_query(
            query="KOSPI OR KOSDAQ OR 한국 증시 OR 원달러 환율 OR 반도체 업황",
            max_age_hours=max_age_hours,
            limit=limit,
            hl="ko",
            gl="KR",
            ceid="KR:ko",
        )
    return fetch_news_by_query(
        query="S&P 500 OR Nasdaq OR Treasury yield OR Federal Reserve OR US stocks",
        max_age_hours=max_age_hours,
        limit=limit,
        hl="en-US",
        gl="US",
        ceid="US:en",
    )


def fetch_market_event_news(market: str, max_age_hours: int, limit: int = 3) -> list[NewsItem]:
    normalized = market.upper()
    if normalized == "KR":
        return fetch_news_by_query(
            query="한국 증시 일정 OR 한국은행 OR 환율 OR 정부 정책 OR 실적 발표",
            max_age_hours=max_age_hours,
            limit=limit,
            hl="ko",
            gl="KR",
            ceid="KR:ko",
        )
    return fetch_news_by_query(
        query="CPI OR FOMC OR payrolls OR earnings OR options expiration OR Treasury yield",
        max_age_hours=max_age_hours,
        limit=limit,
        hl="en-US",
        gl="US",
        ceid="US:en",
    )
