from __future__ import annotations

from app.agents.llm_client import LLMClient
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
            return llm_client.generate_structured(SYSTEM_PROMPT, payload, FinalAnalysis, role="final")
        except Exception:
            pass
    return _fallback_final_analysis(chart_analysis, news_analysis)


def _fallback_final_analysis(chart_analysis: ChartAnalysis, news_analysis: NewsAnalysis) -> FinalAnalysis:
    final_score = int(round(chart_analysis.chart_score * 0.65 + news_analysis.news_score * 0.35))
    action = ActionLabel.OBSERVE
    if final_score >= 70 and chart_analysis.chart_score >= 65:
        action = ActionLabel.CANDIDATE
    elif final_score < 50:
        action = ActionLabel.AVOID

    risks = list(dict.fromkeys((chart_analysis.negative_signals + news_analysis.bearish_points + news_analysis.uncertainties)))[:3]
    confirmations = []
    if chart_analysis.label.value in {"breakout", "pullback"}:
        confirmations.append("Confirm price respects the described setup on the next session.")
    confirmations.append("Check whether fresh news changes the near-term thesis.")
    if not risks:
        risks = ["No single dominant risk was detected, but execution timing still matters."]

    return FinalAnalysis(
        final_score=max(0, min(100, final_score)),
        action_label=action,
        summary_reason=f"Chart score {chart_analysis.chart_score} and news score {news_analysis.news_score} were combined under a chart-first weighting.",
        main_risks=risks,
        what_to_confirm_next=confirmations[:3],
    )
