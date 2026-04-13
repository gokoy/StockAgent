from __future__ import annotations

import json
from pathlib import Path

from app.data.sector_data import infer_sector_name
from app.models.schemas import EvaluatedStock, RunResult


def record_recommendation(run_result: RunResult, performance_dir: Path) -> Path:
    performance_dir.mkdir(parents=True, exist_ok=True)
    target = performance_dir / "recommendations.jsonl"
    existing = load_recommendations(performance_dir)
    deduped: dict[tuple[str, str], dict] = {
        (str(item.get("run_at", "")), str(item.get("ticker", ""))): item for item in existing
    }
    for stock in run_result.candidates + run_result.non_candidates:
        record = _record_for_stock(run_result, stock)
        deduped[(record["run_at"], record["ticker"])] = record
    if deduped:
        ordered = sorted(deduped.values(), key=lambda item: (item.get("run_at", ""), item.get("ticker", "")))
        with target.open("w", encoding="utf-8") as handle:
            for item in ordered:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
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
    section_by_market = {section.market: section for section in run_result.market_sections}
    market_section = section_by_market.get(stock.market)
    return {
        "run_at": run_result.run_at.strftime("%Y-%m-%d"),
        "ticker": stock.ticker,
        "name": stock.name,
        "market": stock.market,
        "sector_name": infer_sector_name(stock.market, stock.ticker),
        "in_holdings": stock.in_holdings,
        "action_label": stock.final_analysis.action_label.value,
        "final_score": stock.final_analysis.final_score,
        "chart_score": stock.chart_analysis.chart_score,
        "news_score": stock.news_analysis.news_score,
        "macro_score": market_section.macro_analysis.macro_score if market_section and market_section.macro_analysis else None,
    }
