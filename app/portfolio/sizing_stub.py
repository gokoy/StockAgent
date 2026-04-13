from __future__ import annotations

from app.models.schemas import CandidateBrief, PortfolioGuidance


def suggest_position_size(final_score: int, macro_score: int, action_label: str, horizon: str) -> dict:
    if action_label not in {"candidate", "observe"}:
        return {"status": "skip", "suggested_weight_pct": 0, "reason": "avoid 상태에서는 신규 비중 제안을 하지 않는다."}

    base = 4 if horizon == "short" else 6
    if final_score >= 80:
        base += 2
    elif final_score < 65:
        base -= 1

    if macro_score >= 65:
        base += 1
    elif macro_score < 45:
        base -= 2

    weight = max(1, min(10, base))
    return {
        "status": "ok",
        "suggested_weight_pct": weight,
        "reason": f"{horizon} 관점 점수와 시장 국면 점수를 함께 반영한 기본 비중 제안이다.",
    }


def build_portfolio_guidance(candidate_briefs: list[CandidateBrief], horizon: str, macro_score: int) -> PortfolioGuidance:
    if not candidate_briefs:
        return PortfolioGuidance(
            horizon=horizon,
            total_suggested_weight_pct=0,
            candidate_count=0,
            max_single_position_pct=0,
            stance="신규 비중 제안 없음",
            notes=["현재 조건에서는 신규 진입보다 관찰 우선이 적절하다."],
        )

    weights = [item.suggested_weight_pct or 0 for item in candidate_briefs]
    total = sum(weights)
    capped_total = min(total, 25 if horizon == "short" else 35)
    max_single = max(weights) if weights else 0

    if macro_score >= 65:
        stance = "공격도 소폭 확대 가능"
    elif macro_score < 45:
        stance = "보수적 비중 운용 권장"
    else:
        stance = "선별적 분할 접근 권장"

    notes = [
        f"{horizon} 관점 기준 총 제안 비중은 {capped_total}%로 제한한다.",
        f"단일 종목 최대 비중은 {max_single}% 기준으로 본다.",
    ]
    if total > capped_total:
        notes.append("후보 수가 많더라도 총합 비중 상한을 우선 적용한다.")

    return PortfolioGuidance(
        horizon=horizon,
        total_suggested_weight_pct=capped_total,
        candidate_count=len(candidate_briefs),
        max_single_position_pct=max_single,
        stance=stance,
        notes=notes,
    )
