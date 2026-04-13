from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.performance import summarize_performance


def run_backtest_stub(performance_dir: Path) -> dict:
    summary = summarize_performance(performance_dir)
    result = {
        "status": "stub_with_live_history_check",
        "evaluated_records": summary.get("count", 0),
        "avg_return_5d": summary.get("avg_return_5d"),
        "avg_return_10d": summary.get("avg_return_10d"),
        "avg_return_20d": summary.get("avg_return_20d"),
        "win_rate_5d": summary.get("win_rate_5d"),
        "win_rate_10d": summary.get("win_rate_10d"),
        "win_rate_20d": summary.get("win_rate_20d"),
        "avg_max_upside_20d": summary.get("avg_max_upside_20d"),
        "avg_max_drawdown_20d": summary.get("avg_max_drawdown_20d"),
        "reward_risk_ratio_20d": summary.get("reward_risk_ratio_20d"),
        "by_action": summary.get("by_action", {}),
        "by_market": summary.get("by_market", {}),
        "by_sector": summary.get("by_sector", {}),
        "by_macro_bucket": summary.get("by_macro_bucket", {}),
        "by_chart_bucket": summary.get("by_chart_bucket", {}),
        "by_setup_combo": summary.get("by_setup_combo", {}),
    }
    target = performance_dir / "backtest_summary.json"
    performance_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
