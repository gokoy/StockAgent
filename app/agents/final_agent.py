from __future__ import annotations

from app.agents.llm_client import LLMClient
from app.config import AppConfig
from app.models.enums import ActionLabel
from app.models.schemas import ChartAnalysis, ChartFeatures, FinalAnalysis, NewsAnalysis


SYSTEM_PROMPT = """
당신은 스윙 투자 보조 도구의 최종 판단 에이전트다.
반드시 제공된 차트 feature, 차트 해석, 뉴스 해석만 결합한다.
새로운 근거나 사실을 만들어내지 않는다.
확신이 약하면 candidate보다 observe 또는 avoid를 우선한다.
설명 문구는 모두 한국어로 작성한다.
유효한 JSON만 반환한다.
""".strip()


def analyze_final_decision(
    ticker: str,
    name: str,
    chart_features: ChartFeatures,
    chart_analysis: ChartAnalysis,
    news_analysis: NewsAnalysis,
    llm_client: LLMClient | None,
    config: AppConfig,
) -> FinalAnalysis:
    payload = {
        "ticker": ticker,
        "name": name,
        "chart_features": chart_features.model_dump(),
        "chart_analysis": chart_analysis.model_dump(mode="json"),
        "news_analysis": news_analysis.model_dump(mode="json"),
    }
    if llm_client:
        try:
            llm_result = llm_client.generate_structured(SYSTEM_PROMPT, payload, FinalAnalysis, role="final")
            return _apply_decision_policy(llm_result, chart_analysis, news_analysis, config)
        except Exception as exc:
            return _fallback_final_analysis(chart_analysis, news_analysis, config, fallback_reason=_fallback_reason(exc))
    return _fallback_final_analysis(chart_analysis, news_analysis, config)


def _fallback_final_analysis(
    chart_analysis: ChartAnalysis,
    news_analysis: NewsAnalysis,
    config: AppConfig,
    fallback_reason: str | None = None,
) -> FinalAnalysis:
    final_score = int(round(chart_analysis.chart_score * 0.65 + news_analysis.news_score * 0.35))
    risks = list(dict.fromkeys((chart_analysis.negative_signals + news_analysis.bearish_points + news_analysis.uncertainties)))[:3]
    confirmations = []
    if chart_analysis.label.value in {"breakout", "pullback"}:
        confirmations.append("다음 거래일에도 설명한 setup이 유지되는지 확인한다.")
    confirmations.append("최신 뉴스가 단기 투자 논리를 바꾸는지 다시 확인한다.")
    if not risks:
        risks = ["지배적인 단일 리스크는 없지만 진입 시점 관리가 여전히 중요하다."]
    if fallback_reason:
        risks = risks[:2] + [f"LLM 최종 판단을 사용할 수 없어 규칙 기반 대체 결과를 사용했다 ({fallback_reason})."]

    result = FinalAnalysis(
        final_score=max(0, min(100, final_score)),
        action_label=ActionLabel.OBSERVE,
        summary_reason=f"차트 점수 {chart_analysis.chart_score}와 뉴스 점수 {news_analysis.news_score}를 차트 비중 우선 방식으로 합산했다.",
        main_risks=risks,
        what_to_confirm_next=confirmations[:3],
    )
    return _apply_decision_policy(result, chart_analysis, news_analysis, config)


def _fallback_reason(exc: Exception) -> str:
    return exc.__class__.__name__.replace("_", " ").lower()


def _apply_decision_policy(
    final_analysis: FinalAnalysis,
    chart_analysis: ChartAnalysis,
    news_analysis: NewsAnalysis,
    config: AppConfig,
) -> FinalAnalysis:
    final_score = final_analysis.final_score
    action = ActionLabel.AVOID
    if (
        final_score >= config.candidate_min_final_score
        and chart_analysis.chart_score >= config.candidate_min_chart_score
        and news_analysis.news_score >= config.candidate_min_news_score
    ):
        action = ActionLabel.CANDIDATE
    elif final_score >= config.observe_min_final_score:
        action = ActionLabel.OBSERVE

    return final_analysis.model_copy(update={"action_label": action})
