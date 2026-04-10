from __future__ import annotations

from app.agents.llm_client import LLMClient
from app.models.enums import ChartLabel, ConfidenceLabel
from app.models.schemas import ChartAnalysis, ChartFeatures


SYSTEM_PROMPT = """
You are a swing trading chart analysis agent.
Use only the provided chart features.
Do not invent facts, prices, patterns, or catalysts.
If evidence is mixed, state uncertainty clearly.
Return valid JSON only.
""".strip()


def analyze_chart(ticker: str, name: str, features: ChartFeatures, llm_client: LLMClient | None) -> ChartAnalysis:
    payload = {"ticker": ticker, "name": name, **features.model_dump()}
    if llm_client:
        try:
            return llm_client.generate_structured(SYSTEM_PROMPT, payload, ChartAnalysis, role="chart")
        except Exception as exc:
            return _fallback_chart_analysis(features, fallback_reason=_fallback_reason(exc))
    return _fallback_chart_analysis(features)


def _fallback_chart_analysis(features: ChartFeatures, fallback_reason: str | None = None) -> ChartAnalysis:
    score = 50
    positives: list[str] = []
    negatives: list[str] = []
    label = ChartLabel.MIXED
    confidence = ConfidenceLabel.MEDIUM

    if features.above_ma20 and features.above_ma60:
        score += 12
        positives.append("Price is holding above MA20 and MA60.")
    if features.breakout_setup:
        score += 15
        positives.append("Price is within reach of the 20-day high with supportive volume.")
        label = ChartLabel.BREAKOUT
    if features.pullback_setup:
        score += 10
        positives.append("Trend is intact and price is near MA20 support.")
        label = ChartLabel.PULLBACK if label == ChartLabel.MIXED else label
    if features.volatility_contracting:
        score += 8
        positives.append("Recent volatility has tightened versus the prior month.")
    if features.range_bound:
        positives.append("Price is trading in a relatively tight 30-day range.")
        label = ChartLabel.RANGE if label == ChartLabel.MIXED else label

    if not features.above_ma120:
        score -= 12
        negatives.append("Price is still below MA120.")
    if features.overextended_pct >= 8:
        score -= 14
        negatives.append("Price is extended materially above MA20.")
        label = ChartLabel.EXTENDED
    if features.recent_sharp_runup:
        score -= 8
        negatives.append("Recent price run-up raises chase risk.")
    if features.volume_ratio_20d < 0.8:
        score -= 10
        negatives.append("Latest volume is soft versus the 20-day average.")
    if features.atr_pct >= 5.5:
        score -= 8
        negatives.append("ATR percentage is elevated for a controlled swing entry.")
        confidence = ConfidenceLabel.LOW
    if fallback_reason:
        negatives.append(f"LLM chart analysis unavailable; deterministic fallback used ({fallback_reason}).")

    score = max(0, min(100, score))
    why_now = positives[0] if positives else "No strong timing edge is visible from current chart features."
    why_not_now = negatives[0] if negatives else "No major chart-based objection stands out."
    invalid_if = f"Setup weakens if price loses the nearby support zone. Hint: {features.support_level_hint}."
    return ChartAnalysis(
        chart_score=score,
        label=label,
        positive_signals=positives[:3],
        negative_signals=negatives[:3],
        why_now=why_now,
        why_not_now=why_not_now,
        invalid_if=invalid_if,
        confidence=confidence,
    )


def _fallback_reason(exc: Exception) -> str:
    return exc.__class__.__name__.replace("_", " ").lower()
