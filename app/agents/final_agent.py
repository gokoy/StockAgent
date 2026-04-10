from __future__ import annotations

from app.agents.llm_client import LLMClient
from app.config import AppConfig
from app.models.enums import ActionLabel
from app.models.schemas import ChartAnalysis, ChartFeatures, FinalAnalysis, NewsAnalysis


SYSTEM_PROMPT = """
You are the final decision agent for a swing trading assistant.
Combine only the supplied chart features, chart analysis, and news analysis.
Do not invent new evidence.
If conviction is weak, prefer observe or avoid over candidate.
Return valid JSON only.
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
        confirmations.append("Confirm price respects the described setup on the next session.")
    confirmations.append("Check whether fresh news changes the near-term thesis.")
    if not risks:
        risks = ["No single dominant risk was detected, but execution timing still matters."]
    if fallback_reason:
        risks = risks[:2] + [f"LLM final analysis unavailable; deterministic fallback used ({fallback_reason})."]

    result = FinalAnalysis(
        final_score=max(0, min(100, final_score)),
        action_label=ActionLabel.OBSERVE,
        summary_reason=f"Chart score {chart_analysis.chart_score} and news score {news_analysis.news_score} were combined under a chart-first weighting.",
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
