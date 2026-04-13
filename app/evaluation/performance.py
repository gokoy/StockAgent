from __future__ import annotations

import json
from pathlib import Path

from app.data.market_data import fetch_forward_close_path, fetch_forward_path_stats
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
            "scenario_tp10_sl5_20d": _simulate_exit_scenario(record["ticker"], record["run_at"], 20, take_profit_pct=10, stop_loss_pct=-5),
            "scenario_tp15_sl7_20d": _simulate_exit_scenario(record["ticker"], record["run_at"], 20, take_profit_pct=15, stop_loss_pct=-7),
        }
        evaluated.append(item)

    summary = {
        "count": len(evaluated),
        "candidate_count": sum(1 for item in evaluated if item.get("action_label") == "candidate"),
        "observe_count": sum(1 for item in evaluated if item.get("action_label") == "observe"),
        "avg_return_5d": _avg([item["return_5d"] for item in evaluated]),
        "avg_return_10d": _avg([item["return_10d"] for item in evaluated]),
        "avg_return_20d": _avg([item["return_20d"] for item in evaluated]),
        "win_rate_5d": _win_rate([item["return_5d"] for item in evaluated]),
        "win_rate_10d": _win_rate([item["return_10d"] for item in evaluated]),
        "win_rate_20d": _win_rate([item["return_20d"] for item in evaluated]),
        "avg_max_upside_20d": _avg([item["max_upside_20d"] for item in evaluated]),
        "avg_max_drawdown_20d": _avg([item["max_drawdown_20d"] for item in evaluated]),
        "reward_risk_ratio_20d": _reward_risk_ratio(
            _avg([item["max_upside_20d"] for item in evaluated]),
            _avg([item["max_drawdown_20d"] for item in evaluated]),
        ),
        "scenario_results": _scenario_summary(evaluated),
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


def _win_rate(values: list[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    wins = [value for value in usable if value > 0]
    return round((len(wins) / len(usable)) * 100, 2)


def _reward_risk_ratio(avg_upside: float | None, avg_drawdown: float | None) -> float | None:
    if avg_upside is None or avg_drawdown is None or avg_drawdown == 0:
        return None
    if avg_drawdown > 0:
        return None
    return round(avg_upside / abs(avg_drawdown), 2)


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
            "win_rate_5d": _win_rate([item["return_5d"] for item in items]),
            "win_rate_10d": _win_rate([item["return_10d"] for item in items]),
            "win_rate_20d": _win_rate([item["return_20d"] for item in items]),
            "avg_max_upside_20d": _avg([item.get("max_upside_20d") for item in items]),
            "avg_max_drawdown_20d": _avg([item.get("max_drawdown_20d") for item in items]),
            "reward_risk_ratio_20d": _reward_risk_ratio(
                _avg([item.get("max_upside_20d") for item in items]),
                _avg([item.get("max_drawdown_20d") for item in items]),
            ),
        }
    return summary


def _simulate_exit_scenario(
    ticker: str,
    start_date: str,
    trading_days: int,
    take_profit_pct: float,
    stop_loss_pct: float,
) -> dict:
    closes = fetch_forward_close_path(ticker, start_date, trading_days)
    if len(closes) < 2:
        return {"result_pct": None, "exit_reason": "insufficient_data", "exit_day": None}
    entry = float(closes[0])
    for idx, close in enumerate(closes[1:], start=1):
        pnl_pct = ((float(close) / entry) - 1.0) * 100
        if pnl_pct >= take_profit_pct:
            return {"result_pct": round(pnl_pct, 2), "exit_reason": "take_profit", "exit_day": idx}
        if pnl_pct <= stop_loss_pct:
            return {"result_pct": round(pnl_pct, 2), "exit_reason": "stop_loss", "exit_day": idx}
    final_pct = ((float(closes[-1]) / entry) - 1.0) * 100
    return {"result_pct": round(final_pct, 2), "exit_reason": "time_exit", "exit_day": len(closes) - 1}


def _scenario_summary(records: list[dict]) -> dict:
    scenarios = ("scenario_tp10_sl5_20d", "scenario_tp15_sl7_20d")
    summary: dict[str, dict] = {}
    for scenario in scenarios:
        items = [record.get(scenario) for record in records if isinstance(record.get(scenario), dict)]
        values = [item.get("result_pct") for item in items if item.get("result_pct") is not None]
        reasons: dict[str, int] = {}
        for item in items:
            reason = str(item.get("exit_reason", "unknown"))
            reasons[reason] = reasons.get(reason, 0) + 1
        summary[scenario] = {
            "count": len(items),
            "avg_result_pct": _avg(values),
            "win_rate": _win_rate(values),
            "exit_reason_counts": reasons,
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
