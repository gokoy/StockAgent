from __future__ import annotations


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
