from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
import re
from urllib.parse import quote_plus

import feedparser
import yfinance as yf

from app.data.disclosure_data import fetch_recent_disclosures
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
    "marketscreener.com",
    "yahoo finance",
}

REUTERS_SOURCES = {
    "reuters",
}


def fetch_latest_news(
    ticker: str,
    name: str,
    market: str,
    max_age_hours: int,
    limit: int = 5,
    opendart_api_key: str | None = None,
) -> list[NewsItem]:
    normalized_market = market.upper()
    if normalized_market == "KR":
        items: list[NewsItem] = []
        items.extend(
            fetch_recent_disclosures(
                ticker=ticker,
                name=name,
                max_age_hours=max_age_hours,
                api_key=opendart_api_key,
                cache_path=_corp_code_cache_path(),
                limit=max(limit, 3),
            )
        )
        items.extend(
            fetch_news_by_query(
                query=f"{name} OR {ticker.replace('.KS', '').replace('.KQ', '')} site:finance.naver.com",
                max_age_hours=max_age_hours,
                limit=max(limit * 4, 12),
                hl="ko",
                gl="KR",
                ceid="KR:ko",
            )
        )
        items.extend(
            fetch_news_by_query(
                query=f"{name} 주식 OR {ticker.replace('.KS', '').replace('.KQ', '')} 종목 뉴스",
                max_age_hours=max_age_hours,
                limit=max(limit * 2, 8),
                hl="ko",
                gl="KR",
                ceid="KR:ko",
            )
        )
        return _rank_stock_news(items, limit=limit, market=normalized_market)

    query = f"{ticker} stock"
    items = fetch_news_by_query(
        query=query,
        max_age_hours=max_age_hours,
        limit=max(limit * 4, 12),
        hl="en-US",
        gl="US",
        ceid="US:en",
    )
    items.extend(fetch_yahoo_ticker_news(ticker, name, max_age_hours=max_age_hours, limit=max(limit * 2, 8)))
    return _rank_stock_news(items, limit=limit, market=normalized_market)


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


def _rank_stock_news(items: list[NewsItem], limit: int, market: str = "US") -> list[NewsItem]:
    seen: set[str] = set()
    source_counts: dict[str, int] = {}
    scored: list[tuple[int, NewsItem]] = []
    for item in items:
        dedupe_key = _headline_dedupe_key(item.headline)
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        score = _score_stock_news_item(item, market=market)
        if score <= 0:
            continue
        source_key = _normalized_source(item.source)
        if source_key:
            if source_counts.get(source_key, 0) >= 1:
                continue
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
        scored.append((score, item))
    scored.sort(key=lambda pair: (_source_priority(pair[1].source), pair[0], pair[1].published_at), reverse=True)
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
        source_key = _normalized_source(item.source)
        if source_key:
            max_per_source = 1 if event_mode else 2
            if source_counts.get(source_key, 0) >= max_per_source:
                continue
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
        scored.append((score, item))
    scored.sort(key=lambda pair: (_source_priority(pair[1].source), pair[0], pair[1].published_at), reverse=True)
    return [item for _, item in scored]


def fetch_yahoo_ticker_news(ticker: str, name: str, max_age_hours: int, limit: int = 5) -> list[NewsItem]:
    try:
        raw_items = getattr(yf.Ticker(ticker), "news", None) or []
    except Exception:
        return []
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    name_token = (name.split()[0] if name else ticker).lower()
    relevance_tokens = {ticker.lower(), name_token}
    items: list[NewsItem] = []
    for raw in raw_items:
        content = raw.get("content", {})
        if not isinstance(content, dict):
            continue
        title = str(content.get("title", "")).strip()
        summary = str(content.get("summary", "")).strip()
        published_raw = content.get("pubDate") or content.get("displayTime")
        if not title or not published_raw:
            continue
        try:
            published_at = datetime.fromisoformat(str(published_raw).replace("Z", "+00:00")).astimezone(UTC)
        except Exception:
            continue
        if published_at < cutoff:
            continue
        haystack = f"{title} {summary}".lower()
        if not any(token and token in haystack for token in relevance_tokens):
            storyline = content.get("storyline", {})
            if not isinstance(storyline, dict) or ticker.lower() not in str(storyline).lower():
                continue
        provider = content.get("provider", {}) if isinstance(content.get("provider"), dict) else {}
        canonical = content.get("canonicalUrl", {}) if isinstance(content.get("canonicalUrl"), dict) else {}
        items.append(
            NewsItem(
                headline=title,
                summary=(summary or title)[:400],
                published_at=published_at,
                source=str(provider.get("displayName", "Yahoo Finance")).strip() or "Yahoo Finance",
                url=str(canonical.get("url", "")).strip(),
            )
        )
        if len(items) >= limit:
            break
    return items


def _score_market_news_item(item: NewsItem, market: str, event_mode: bool) -> int:
    text = f"{item.headline} {item.summary}".lower()
    headline = item.headline.lower().strip()
    keywords = KR_MARKET_KEYWORDS if market == "KR" else US_MARKET_KEYWORDS
    noise_keywords = KR_NOISE_KEYWORDS if market == "KR" else US_NOISE_KEYWORDS
    score = 0

    for keyword in keywords:
        if keyword in text:
            score += 3 if event_mode else 2

    for keyword in noise_keywords:
        if keyword in text:
            score -= 3

    if market == "KR" and _is_low_value_kr_headline(item.headline):
        return -100

    if market == "US" and any(pattern in text for pattern in ("etf", "dividend etf", "nyse |", "new york stock exchange |")):
        return -100

    if market == "US" and any(
        pattern in headline
        for pattern in (
            "us stock market today:",
            "stock market today:",
            "dow falls",
            "s&p 500 futures edge higher",
            "what should investor know",
            "why are us stock market futures up today",
            "will s&p 500, dow jones and nasdaq stay in green",
            "us stocks today:",
        )
    ):
        return -100

    if market == "US" and any(
        source in _normalized_source(item.source)
        for source in ("yahoo finance australia", "the sunday guardian", "economy middle east", "msn", "the economic times")
    ):
        return -100

    if "cpi" in text or "fomc" in text or "yield" in text or "실적" in text or "환율" in text:
        score += 2
    if item.source:
        source = _normalized_source(item.source)
        score += 1
        if _source_matches(source, REUTERS_SOURCES):
            score += 5
        if _source_matches(source, HIGH_SIGNAL_SOURCES):
            score += 2
        if _source_matches(source, LOW_SIGNAL_SOURCES):
            return -100
    if market == "US" and any(word in text for word in ("tariff", "hormuz", "geopolitical", "oil")):
        score += 1
    return score


def _score_stock_news_item(item: NewsItem, market: str) -> int:
    text = f"{item.headline} {item.summary}".lower()
    source = _normalized_source(item.source)
    if source == "opendart":
        return 100
    if _source_matches(source, LOW_SIGNAL_SOURCES):
        return -100
    if market.upper() == "KR" and _is_low_value_kr_headline(item.headline):
        return -100

    score = 1
    if _source_matches(source, REUTERS_SOURCES):
        score += 6
    elif _source_matches(source, HIGH_SIGNAL_SOURCES):
        score += 3
    elif source:
        score += 1

    low_signal_patterns = (
        "top stocks to buy",
        "prediction:",
        "stock quote price and forecast",
        "stock quote",
        "price target",
        "forecast -",
        "forecast:",
        "stock quote and forecast",
        "stock reports earnings",
        "turns positive for 2026",
        "jim cramer",
        "best stock",
        "stocks to buy",
        "price prediction",
        "is it time to buy",
        "reports earnings!!!",
    )
    for pattern in low_signal_patterns:
        if pattern in text:
            score -= 3

    if "valuation after strong recent share price momentum" in text:
        score -= 3
    if source == "msn" and any(pattern in text for pattern in ("stock quote", "forecast", "price target")):
        return -100
    if source == "cnn" and "forecast" in text:
        return -100

    if any(word in text for word in ("earnings", "guidance", "forecast", "revenue", "deal", "data center", "chip", "ai", "공시", "수주", "유상증자", "공급계약")):
        score += 2
    if any(word in text for word in ("lawsuit", "probe", "downgrade", "cut", "delay", "tariff")):
        score += 1
    if market.upper() == "KR" and "site:finance.naver.com" in text:
        score += 1
    return score


def _is_low_value_kr_headline(headline: str) -> bool:
    normalized = re.sub(r"\s+", " ", headline.strip().lower())
    if not normalized:
        return True
    if normalized in {"- 네이버 증권", "네이버 증권", "097950 - 네이버 증권"}:
        return True
    if normalized in {
        "네이버 증권 - 네이버 증권",
        "주가 - 네이버 증권 - naver - 네이버 증권",
    }:
        return True
    if re.fullmatch(r"\d{6}(\.\w+)? - 네이버 증권", normalized):
        return True
    if "네이버 증권 - naver - 네이버 증권" in normalized:
        return True
    if normalized.endswith("- 네이버 증권") and ("주가" in normalized or "naver -" in normalized):
        return True
    if normalized.endswith("- 네이버 증권") and re.search(r"\d{6}|주가|종목", normalized):
        return True
    if normalized.count("네이버 증권") >= 2:
        return True
    return False


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


def _source_priority(source: str) -> int:
    normalized = _normalized_source(source)
    if normalized == "opendart":
        return 4
    if _source_matches(normalized, REUTERS_SOURCES):
        return 3
    if _source_matches(normalized, HIGH_SIGNAL_SOURCES):
        return 2
    if normalized:
        return 1
    return 0


def _corp_code_cache_path():
    from pathlib import Path

    return Path(__file__).resolve().parents[2] / "data" / "inputs" / "opendart_corp_codes.json"
