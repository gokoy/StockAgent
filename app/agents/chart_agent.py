from __future__ import annotations

from app.agents.llm_client import LLMClient
from app.models.enums import ChartLabel, ConfidenceLabel
from app.models.schemas import ChartAnalysis, ChartFeatures


SYSTEM_PROMPT = """
당신은 스윙 투자용 차트 해석 에이전트다.
반드시 제공된 차트 feature만 사용한다.
주어지지 않은 사실, 가격, 패턴, 재료를 만들어내지 않는다.
근거가 엇갈리면 불확실성을 분명히 적는다.
설명 문구는 모두 한국어로 작성한다.
유효한 JSON만 반환한다.
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
        positives.append("주가가 MA20과 MA60 위에서 유지되고 있다.")
    if features.breakout_setup:
        score += 15
        positives.append("거래량이 뒷받침되며 20일 고점 돌파 구간에 근접해 있다.")
        label = ChartLabel.BREAKOUT
    if features.pullback_setup:
        score += 10
        positives.append("추세가 유지된 상태에서 MA20 지지 구간에 가깝다.")
        label = ChartLabel.PULLBACK if label == ChartLabel.MIXED else label
    if features.volatility_contracting:
        score += 8
        positives.append("최근 변동성이 이전 구간 대비 축소되고 있다.")
    if features.range_bound:
        positives.append("최근 30일 동안 비교적 좁은 박스권에서 움직이고 있다.")
        label = ChartLabel.RANGE if label == ChartLabel.MIXED else label

    if not features.above_ma120:
        score -= 12
        negatives.append("주가가 아직 MA120 아래에 있다.")
    if features.overextended_pct >= 8:
        score -= 14
        negatives.append("주가가 MA20 대비 과하게 이격돼 있다.")
        label = ChartLabel.EXTENDED
    if features.recent_sharp_runup:
        score -= 8
        negatives.append("최근 급등으로 추격 매수 위험이 커졌다.")
    if features.volume_ratio_20d < 0.8:
        score -= 10
        negatives.append("최근 거래량이 20일 평균 대비 약하다.")
    if features.atr_pct >= 5.5:
        score -= 8
        negatives.append("ATR 비율이 높아 스윙 진입 기준으로는 변동성이 크다.")
        confidence = ConfidenceLabel.LOW
    if fallback_reason:
        negatives.append(f"LLM 차트 해석을 사용할 수 없어 규칙 기반 대체 결과를 사용했다 ({fallback_reason}).")

    score = max(0, min(100, score))
    why_now = positives[0] if positives else "현재 차트 feature만으로는 뚜렷한 진입 타이밍 우위가 보이지 않는다."
    why_not_now = negatives[0] if negatives else "차트상 치명적인 반대 근거는 아직 두드러지지 않는다."
    invalid_if = f"주가가 인접 지지 구간을 이탈하면 setup이 약해진다. 힌트: {features.support_level_hint}."
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
