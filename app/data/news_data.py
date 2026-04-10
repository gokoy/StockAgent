from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser

from app.models.schemas import NewsItem


def fetch_latest_news(ticker: str, name: str, max_age_hours: int, limit: int = 5) -> list[NewsItem]:
    query = quote_plus(f"{ticker} stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
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
