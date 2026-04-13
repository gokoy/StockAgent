from __future__ import annotations

from pathlib import Path

from app.evaluation.performance import summarize_performance


def run_backtest_stub(performance_dir: Path) -> dict:
    summary = summarize_performance(performance_dir)
    return {
        "status": "stub_with_live_history_check",
        "evaluated_records": summary.get("count", 0),
        "avg_return_5d": summary.get("avg_return_5d"),
        "avg_return_10d": summary.get("avg_return_10d"),
        "avg_return_20d": summary.get("avg_return_20d"),
        "by_action": summary.get("by_action", {}),
        "by_market": summary.get("by_market", {}),
        "by_sector": summary.get("by_sector", {}),
        "by_macro_bucket": summary.get("by_macro_bucket", {}),
        "by_chart_bucket": summary.get("by_chart_bucket", {}),
    }
