from __future__ import annotations

from app.agents.llm_client import LLMClient
from app.models.schemas import NewsAnalysis, NewsItem


SYSTEM_PROMPT = """
You are a swing trading news analysis agent.
Use only the supplied recent headlines and summaries.
Do not infer undisclosed fundamentals or events.
Call out uncertainty when coverage is thin.
Return valid JSON only.
""".strip()


def analyze_news(ticker: str, name: str, news_items: list[NewsItem], llm_client: LLMClient | None) -> NewsAnalysis:
    payload = {
        "ticker": ticker,
        "name": name,
        "as_of": news_items[0].published_at.isoformat() if news_items else None,
        "headlines": [item.headline for item in news_items],
        "summaries": [item.summary for item in news_items],
        "published_at": [item.published_at.isoformat() for item in news_items],
    }
    if llm_client:
        try:
            return llm_client.generate_structured(SYSTEM_PROMPT, payload, NewsAnalysis, role="news")
        except Exception:
            pass
    return _fallback_news_analysis(news_items)


def _fallback_news_analysis(news_items: list[NewsItem]) -> NewsAnalysis:
    if not news_items:
        return NewsAnalysis(
            news_score=45,
            bullish_points=[],
            bearish_points=[],
            uncertainties=["Recent news coverage is limited or unavailable."],
            headline_summary="No qualifying recent headlines were found.",
            event_risk="Event risk is unclear because recent coverage is sparse.",
        )

    bullish: list[str] = []
    bearish: list[str] = []
    uncertainties: list[str] = []
    score = 50
    joined = " ".join(f"{item.headline} {item.summary}".lower() for item in news_items)

    bullish_terms = ["beat", "record", "growth", "upgrade", "partnership", "launch", "expansion"]
    bearish_terms = ["miss", "lawsuit", "probe", "downgrade", "delay", "cut", "investigation"]

    for term in bullish_terms:
        if term in joined:
            bullish.append(f"Recent coverage mentions {term}-type positive catalysts.")
            score += 6
            break
    for term in bearish_terms:
        if term in joined:
            bearish.append(f"Recent coverage mentions {term}-type downside risk.")
            score -= 10
            break

    if len(news_items) < 2:
        uncertainties.append("Signal quality is limited because only one recent article qualified.")
        score -= 4

    score = max(0, min(100, score))
    summary = "; ".join(item.headline for item in news_items[:2])
    risk = bearish[0] if bearish else "No single headline dominates risk, but headline risk remains."
    return NewsAnalysis(
        news_score=score,
        bullish_points=bullish[:2],
        bearish_points=bearish[:2],
        uncertainties=uncertainties[:2],
        headline_summary=summary,
        event_risk=risk,
    )
