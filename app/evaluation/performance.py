from __future__ import annotations

import json
from pathlib import Path

from app.data.market_data import fetch_forward_return
from app.evaluation.tracker import load_recommendations


def summarize_performance(performance_dir: Path) -> dict:
    records = load_recommendations(performance_dir)
    evaluated: list[dict] = []
    for record in records:
        if record.get("action_label") not in {"candidate", "observe"}:
            continue
        item = {
            **record,
            "return_5d": fetch_forward_return(record["ticker"], record["run_at"], 5),
            "return_10d": fetch_forward_return(record["ticker"], record["run_at"], 10),
            "return_20d": fetch_forward_return(record["ticker"], record["run_at"], 20),
        }
        evaluated.append(item)

    summary = {
        "count": len(evaluated),
        "candidate_count": sum(1 for item in evaluated if item.get("action_label") == "candidate"),
        "observe_count": sum(1 for item in evaluated if item.get("action_label") == "observe"),
        "avg_return_5d": _avg([item["return_5d"] for item in evaluated]),
        "avg_return_10d": _avg([item["return_10d"] for item in evaluated]),
        "avg_return_20d": _avg([item["return_20d"] for item in evaluated]),
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
