from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import EvaluatedStock, RunResult


def record_recommendation(run_result: RunResult, performance_dir: Path) -> Path:
    performance_dir.mkdir(parents=True, exist_ok=True)
    target = performance_dir / "recommendations.jsonl"
    lines: list[str] = []
    for stock in run_result.candidates + run_result.non_candidates:
        lines.append(json.dumps(_record_for_stock(run_result, stock), ensure_ascii=False))
    if lines:
        with target.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
    return target


def load_recommendations(performance_dir: Path) -> list[dict]:
    target = performance_dir / "recommendations.jsonl"
    if not target.exists():
        return []
    records: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except Exception:
            continue
    return records


def _record_for_stock(run_result: RunResult, stock: EvaluatedStock) -> dict:
    return {
        "run_at": run_result.run_at.strftime("%Y-%m-%d"),
        "ticker": stock.ticker,
        "name": stock.name,
        "market": stock.market,
        "in_holdings": stock.in_holdings,
        "action_label": stock.final_analysis.action_label.value,
        "final_score": stock.final_analysis.final_score,
        "chart_score": stock.chart_analysis.chart_score,
        "news_score": stock.news_analysis.news_score,
    }
