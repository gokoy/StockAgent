from __future__ import annotations

from app.models.schemas import MacroSnapshot, MarketBriefing, MarketIndexSnapshot, MarketRegimeAnalysis


def analyze_market_regime(market_briefing: MarketBriefing) -> MarketRegimeAnalysis:
    positive_signals = sum(1 for item in market_briefing.index_snapshots if item.change_pct > 0)
    negative_signals = sum(1 for item in market_briefing.index_snapshots if item.change_pct < 0)
    risk_flags = list(market_briefing.key_events[:4])

    if positive_signals > negative_signals and market_briefing.strong_sectors:
        regime = "risk_on"
        posture = "강한 종목 위주로 선별 접근"
    elif negative_signals > positive_signals:
        regime = "risk_off"
        posture = "신규 진입보다 보유 점검 우선"
    else:
        regime = "mixed"
        posture = "추격 매수보다 확인 후 접근"

    macro_score = _score_market(market_briefing.index_snapshots, market_briefing.macro_snapshots)
    summary = market_briefing.market_summary.strip() or _fallback_summary(market_briefing, regime)
    if market_briefing.strong_sectors:
        summary = f"{summary} 주도 섹터는 {', '.join(market_briefing.strong_sectors[:2])}다."

    return MarketRegimeAnalysis(
        market_regime=regime,
        macro_score=macro_score,
        market_summary=summary,
        risk_flags=risk_flags,
        recommended_posture=posture,
    )


def _score_market(index_snapshots: list[MarketIndexSnapshot], macro_snapshots: list[MacroSnapshot]) -> int:
    score = 50
    score += sum(4 for item in index_snapshots if item.change_pct > 0)
    score -= sum(4 for item in index_snapshots if item.change_pct < 0)

    for macro in macro_snapshots:
        if macro.symbol in {"^TNX", "DX-Y.NYB"} and macro.change_pct > 0:
            score -= 3
        elif macro.symbol == "CL=F" and macro.change_pct > 0:
            score -= 1
        else:
            score += 1

    return max(0, min(100, score))


def _fallback_summary(market_briefing: MarketBriefing, regime: str) -> str:
    if regime == "risk_on":
        return "주요 지수와 섹터 흐름이 상대적으로 우호적이다."
    if regime == "risk_off":
        return "지수와 매크로 흐름이 보수적이라 신규 진입보다 방어가 우선이다."
    return "지수와 매크로 흐름이 혼재돼 있어 선별 접근이 필요하다."
