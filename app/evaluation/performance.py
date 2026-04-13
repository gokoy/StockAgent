from __future__ import annotations

import json
from pathlib import Path

from app.data.market_data import fetch_forward_path_stats
from app.evaluation.tracker import load_recommendations


def summarize_performance(performance_dir: Path) -> dict:
    records = load_recommendations(performance_dir)
    evaluated: list[dict] = []
    for record in records:
        if record.get("action_label") not in {"candidate", "observe"}:
            continue
        path_5d = fetch_forward_path_stats(record["ticker"], record["run_at"], 5)
        path_10d = fetch_forward_path_stats(record["ticker"], record["run_at"], 10)
        path_20d = fetch_forward_path_stats(record["ticker"], record["run_at"], 20)
        item = {
            **record,
            "return_5d": path_5d["return_5d"],
            "return_10d": path_10d["return_10d"],
            "return_20d": path_20d["return_20d"],
            "max_upside_20d": path_20d["max_upside_20d"],
            "max_drawdown_20d": path_20d["max_drawdown_20d"],
        }
        evaluated.append(item)

    summary = {
        "count": len(evaluated),
        "candidate_count": sum(1 for item in evaluated if item.get("action_label") == "candidate"),
        "observe_count": sum(1 for item in evaluated if item.get("action_label") == "observe"),
        "avg_return_5d": _avg([item["return_5d"] for item in evaluated]),
        "avg_return_10d": _avg([item["return_10d"] for item in evaluated]),
        "avg_return_20d": _avg([item["return_20d"] for item in evaluated]),
        "avg_max_upside_20d": _avg([item["max_upside_20d"] for item in evaluated]),
        "avg_max_drawdown_20d": _avg([item["max_drawdown_20d"] for item in evaluated]),
        "by_action": _group_summary(evaluated, key="action_label"),
        "by_market": _group_summary(evaluated, key="market"),
        "by_sector": _group_summary(evaluated, key_func=_sector_name),
        "by_macro_bucket": _group_summary(evaluated, key_func=_macro_bucket),
        "by_chart_bucket": _group_summary(evaluated, key_func=_chart_bucket),
        "by_setup_combo": _group_summary(evaluated, key_func=_setup_combo),
        "records": evaluated[-50:],
    }
    target = performance_dir / "performance_summary.json"
    performance_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _avg(values: list[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 2)


def _group_summary(records: list[dict], key: str | None = None, key_func=None) -> dict:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        group_key = key_func(record) if key_func else str(record.get(key, "unknown"))
        grouped.setdefault(group_key, []).append(record)
    summary: dict[str, dict] = {}
    for group_key, items in grouped.items():
        summary[group_key] = {
            "count": len(items),
            "avg_return_5d": _avg([item["return_5d"] for item in items]),
            "avg_return_10d": _avg([item["return_10d"] for item in items]),
            "avg_return_20d": _avg([item["return_20d"] for item in items]),
            "avg_max_upside_20d": _avg([item.get("max_upside_20d") for item in items]),
            "avg_max_drawdown_20d": _avg([item.get("max_drawdown_20d") for item in items]),
        }
    return summary


def _chart_bucket(record: dict) -> str:
    chart_score = int(record.get("chart_score", 0))
    if chart_score >= 70:
        return "chart_strong"
    if chart_score >= 55:
        return "chart_mid"
    return "chart_weak"


def _sector_name(record: dict) -> str:
    return str(record.get("sector_name") or "sector_unknown")


def _macro_bucket(record: dict) -> str:
    macro_score = record.get("macro_score")
    if macro_score is None:
        return "macro_unknown"
    value = int(macro_score)
    if value >= 65:
        return "macro_risk_on"
    if value >= 50:
        return "macro_neutral"
    return "macro_cautious"


def _setup_combo(record: dict) -> str:
    parts: list[str] = []
    if record.get("above_ma120"):
        parts.append("long_trend")
    elif record.get("above_ma60"):
        parts.append("mid_trend")
    else:
        parts.append("weak_trend")
    if record.get("breakout_setup"):
        parts.append("breakout")
    elif record.get("pullback_setup"):
        parts.append("pullback")
    if record.get("volatility_contracting"):
        parts.append("contracting")
    if record.get("recent_sharp_runup"):
        parts.append("sharp_runup")
    return "+".join(parts)
