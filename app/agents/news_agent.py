from __future__ import annotations

from app.agents.llm_client import LLMClient
from app.models.schemas import NewsAnalysis, NewsItem


SYSTEM_PROMPT = """
당신은 스윙 투자용 뉴스 해석 에이전트다.
반드시 제공된 최신 기사 제목과 요약만 사용한다.
주어지지 않은 펀더멘털, 실적, 이벤트를 추정하지 않는다.
기사 수가 적거나 근거가 약하면 불확실성을 분명히 적는다.
설명 문구는 모두 한국어로 작성한다.
유효한 JSON만 반환한다.
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
        except Exception as exc:
            return _fallback_news_analysis(news_items, fallback_reason=_fallback_reason(exc))
    return _fallback_news_analysis(news_items)


def _fallback_news_analysis(news_items: list[NewsItem], fallback_reason: str | None = None) -> NewsAnalysis:
    if not news_items:
        uncertainties = ["최근 뉴스 커버리지가 부족하거나 확인되지 않았다."]
        if fallback_reason:
            uncertainties.append(f"LLM 뉴스 해석을 사용할 수 없어 규칙 기반 대체 결과를 사용했다 ({fallback_reason}).")
        return NewsAnalysis(
            news_score=45,
            bullish_points=[],
            bearish_points=[],
            uncertainties=uncertainties[:2],
            headline_summary="조건에 맞는 최신 뉴스가 확인되지 않았다.",
            event_risk="최근 뉴스가 부족해 이벤트 리스크를 명확히 판단하기 어렵다.",
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
            bullish.append(f"최근 기사에서 {term} 성격의 긍정 신호가 확인된다.")
            score += 6
            break
    for term in bearish_terms:
        if term in joined:
            bearish.append(f"최근 기사에서 {term} 성격의 하방 리스크가 언급된다.")
            score -= 10
            break

    if len(news_items) < 2:
        uncertainties.append("조건에 맞는 최신 기사가 1건뿐이라 뉴스 신호의 신뢰도가 낮다.")
        score -= 4
    if fallback_reason:
        uncertainties.append(f"LLM 뉴스 해석을 사용할 수 없어 규칙 기반 대체 결과를 사용했다 ({fallback_reason}).")

    score = max(0, min(100, score))
    summary = "; ".join(item.headline for item in news_items[:2])
    risk = bearish[0] if bearish else "특정 기사 하나가 지배적인 리스크는 아니지만 뉴스 변동성은 남아 있다."
    return NewsAnalysis(
        news_score=score,
        bullish_points=bullish[:2],
        bearish_points=bearish[:2],
        uncertainties=uncertainties[:2],
        headline_summary=summary,
        event_risk=risk,
    )


def _fallback_reason(exc: Exception) -> str:
    return exc.__class__.__name__.replace("_", " ").lower()
