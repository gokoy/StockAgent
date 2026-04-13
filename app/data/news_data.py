from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
import re
from urllib.parse import quote_plus

import feedparser

from app.models.schemas import NewsItem

US_MARKET_KEYWORDS = (
    "s&p 500",
    "nasdaq",
    "dow",
    "russell",
    "treasury",
    "yield",
    "federal reserve",
    "fed",
    "cpi",
    "ppi",
    "payroll",
    "inflation",
    "earnings",
    "oil",
    "dollar",
)

KR_MARKET_KEYWORDS = (
    "kospi",
    "kosdaq",
    "한국 증시",
    "외국인",
    "기관",
    "개인",
    "환율",
    "원달러",
    "반도체",
    "수출",
    "금리",
    "정책",
    "공시",
    "실적",
)

US_NOISE_KEYWORDS = (
    "etf",
    "dividend etf",
    "covered call",
    "penny stock",
    "top stocks to buy",
)

KR_NOISE_KEYWORDS = (
    "추천주",
    "급등주",
    "테마주",
)

LOW_SIGNAL_SOURCES = {
    "ad hoc news",
    "finimize",
    "aol.com",
    "invezz",
    "thestreet.com",
    "the street",
    "benzinga",
    "futubull",
    "富途牛牛",
    "the motley fool",
    "motley fool",
    "zacks",
    "simplywall.st",
    "quiver quantitative",
    "tikr.com",
    "nyse",
    "seeking alpha",
    "mshale",
    "nai500",
    "tipranks",
    "marketbeat",
}

HIGH_SIGNAL_SOURCES = {
    "reuters",
    "bloomberg.com",
    "cnbc",
    "wsj",
    "the wall street journal",
    "financial times",
    "marketwatch",
    "ap news",
    "associated press",
    "msn",
    "marketscreener.com",
    "yahoo finance",
}


def fetch_latest_news(ticker: str, name: str, max_age_hours: int, limit: int = 5) -> list[NewsItem]:
    query = f"{ticker} stock"
    items = fetch_news_by_query(
        query=query,
        max_age_hours=max_age_hours,
        limit=max(limit * 4, 12),
        hl="en-US",
        gl="US",
        ceid="US:en",
    )
    return _rank_stock_news(items, limit=limit)


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
        items = fetch_news_by_query(
            query="KOSPI OR KOSDAQ OR 한국 증시 OR 원달러 환율 OR 반도체 업황",
            max_age_hours=max_age_hours,
            limit=max(limit * 3, 10),
            hl="ko",
            gl="KR",
            ceid="KR:ko",
        )
        return _rank_market_news(items, market=normalized, limit=limit)
    items = fetch_news_by_query(
        query="S&P 500 OR Nasdaq OR Treasury yield OR Federal Reserve OR US stocks",
        max_age_hours=max_age_hours,
        limit=max(limit * 3, 10),
        hl="en-US",
        gl="US",
        ceid="US:en",
    )
    return _rank_market_news(items, market=normalized, limit=limit)


def fetch_market_event_news(market: str, max_age_hours: int, limit: int = 3) -> list[NewsItem]:
    normalized = market.upper()
    if normalized == "KR":
        items = fetch_news_by_query(
            query="한국 증시 일정 OR 한국은행 OR 환율 OR 정부 정책 OR 실적 발표",
            max_age_hours=max_age_hours,
            limit=max(limit * 3, 9),
            hl="ko",
            gl="KR",
            ceid="KR:ko",
        )
        return _rank_event_news(items, market=normalized, limit=limit)
    items = fetch_news_by_query(
        query="CPI OR FOMC OR payrolls OR earnings OR options expiration OR Treasury yield",
        max_age_hours=max_age_hours,
        limit=max(limit * 3, 9),
        hl="en-US",
        gl="US",
        ceid="US:en",
    )
    return _rank_event_news(items, market=normalized, limit=limit)


def _rank_market_news(items: list[NewsItem], market: str, limit: int) -> list[NewsItem]:
    ranked = _rank_news(items, market=market, event_mode=False)
    return ranked[:limit]


def _rank_event_news(items: list[NewsItem], market: str, limit: int) -> list[NewsItem]:
    ranked = _rank_news(items, market=market, event_mode=True)
    return ranked[:limit]


def _rank_stock_news(items: list[NewsItem], limit: int) -> list[NewsItem]:
    seen: set[str] = set()
    source_counts: dict[str, int] = {}
    scored: list[tuple[int, NewsItem]] = []
    for item in items:
        dedupe_key = _headline_dedupe_key(item.headline)
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        score = _score_stock_news_item(item)
        if score <= 0:
            continue
        source_key = _normalized_source(item.source)
        if source_key:
            if source_counts.get(source_key, 0) >= 1:
                continue
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
        scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], pair[1].published_at), reverse=True)
    return [item for _, item in scored[:limit]]


def _rank_news(items: list[NewsItem], market: str, event_mode: bool) -> list[NewsItem]:
    seen: set[str] = set()
    source_counts: dict[str, int] = {}
    scored: list[tuple[int, NewsItem]] = []
    for item in items:
        dedupe_key = _headline_dedupe_key(item.headline)
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        score = _score_market_news_item(item, market=market, event_mode=event_mode)
        if score <= 0:
            continue
        source_key = item.source.strip().lower()
        if source_key:
            max_per_source = 1 if event_mode else 2
            if source_counts.get(source_key, 0) >= max_per_source:
                continue
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
        scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], pair[1].published_at), reverse=True)
    return [item for _, item in scored]


def _score_market_news_item(item: NewsItem, market: str, event_mode: bool) -> int:
    text = f"{item.headline} {item.summary}".lower()
    keywords = KR_MARKET_KEYWORDS if market == "KR" else US_MARKET_KEYWORDS
    noise_keywords = KR_NOISE_KEYWORDS if market == "KR" else US_NOISE_KEYWORDS
    score = 0

    for keyword in keywords:
        if keyword in text:
            score += 3 if event_mode else 2

    for keyword in noise_keywords:
        if keyword in text:
            score -= 3

    if market == "US" and any(pattern in text for pattern in ("etf", "dividend etf", "nyse |", "new york stock exchange |")):
        return -100

    if "cpi" in text or "fomc" in text or "yield" in text or "실적" in text or "환율" in text:
        score += 2
    if item.source:
        source = _normalized_source(item.source)
        score += 1
        if _source_matches(source, HIGH_SIGNAL_SOURCES):
            score += 2
        if _source_matches(source, LOW_SIGNAL_SOURCES):
            return -100
    if market == "US" and any(word in text for word in ("tariff", "hormuz", "geopolitical", "oil")):
        score += 1
    return score


def _score_stock_news_item(item: NewsItem) -> int:
    text = f"{item.headline} {item.summary}".lower()
    source = _normalized_source(item.source)
    if _source_matches(source, LOW_SIGNAL_SOURCES):
        return -100

    score = 1
    if _source_matches(source, HIGH_SIGNAL_SOURCES):
        score += 3
    elif source:
        score += 1

    low_signal_patterns = (
        "top stocks to buy",
        "prediction:",
        "jim cramer",
        "best stock",
        "stocks to buy",
        "price prediction",
        "is it time to buy",
    )
    for pattern in low_signal_patterns:
        if pattern in text:
            score -= 3

    if "valuation after strong recent share price momentum" in text:
        score -= 3

    if any(word in text for word in ("earnings", "guidance", "forecast", "revenue", "deal", "data center", "chip", "ai")):
        score += 2
    if any(word in text for word in ("lawsuit", "probe", "downgrade", "cut", "delay", "tariff")):
        score += 1
    return score


def _headline_dedupe_key(headline: str) -> str:
    normalized = re.sub(r"[^a-z0-9가-힣 ]+", " ", headline.lower())
    tokens = [token for token in normalized.split() if token]
    stopwords = {"the", "a", "an", "after", "ahead", "with", "and", "as", "in", "on", "of"}
    tokens = [token for token in tokens if token not in stopwords]
    return " ".join(tokens[:8])


def _normalized_source(source: str) -> str:
    return re.sub(r"\s+", " ", source.strip().lower())


def _source_matches(source: str, candidates: set[str]) -> bool:
    if not source:
        return False
    return any(candidate in source for candidate in candidates)
