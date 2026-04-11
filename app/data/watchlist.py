from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.models.enums import ActionLabel
from app.models.schemas import RunResult, WatchlistEntry, WatchlistState


def load_watchlist(path: Path) -> WatchlistState:
    if not path.exists():
        return WatchlistState(updated_at=datetime.now().astimezone(), entries=[])
    payload = json.loads(path.read_text(encoding="utf-8"))
    return WatchlistState.model_validate(payload)


def save_watchlist(state: WatchlistState, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path


def update_watchlist_from_run(
    state: WatchlistState,
    run_result: RunResult,
    max_weak_runs: int,
) -> WatchlistState:
    entries = {entry.ticker.upper(): entry for entry in state.entries}
    seen: set[str] = set()

    for stock in run_result.candidates + run_result.non_candidates:
        key = stock.ticker.upper()
        seen.add(key)
        existing = entries.get(key)
        action = stock.final_analysis.action_label
        if existing is None and action in {ActionLabel.CANDIDATE, ActionLabel.OBSERVE}:
            entries[key] = WatchlistEntry(
                ticker=stock.ticker,
                name=stock.name,
                market="KR" if stock.ticker.endswith((".KS", ".KQ")) else "US",
                added_at=run_result.run_at,
                last_seen_at=run_result.run_at,
                last_action=action.value,
                consecutive_weak_runs=0,
                note=f"Auto-added from scan with score {stock.final_analysis.final_score}.",
            )
            continue
        if existing is None:
            continue
        entries[key] = _update_existing_entry(existing, stock.final_analysis.action_label, run_result.run_at, max_weak_runs)

    for key, entry in entries.items():
        if key in seen or not entry.active:
            continue
        entry.last_seen_at = run_result.run_at

    updated = sorted(entries.values(), key=lambda item: (not item.active, item.market, item.ticker))
    return WatchlistState(updated_at=run_result.run_at, entries=updated)


def _update_existing_entry(
    entry: WatchlistEntry,
    action: ActionLabel,
    run_at: datetime,
    max_weak_runs: int,
) -> WatchlistEntry:
    weak_runs = entry.consecutive_weak_runs
    active = entry.active
    note = entry.note
    if action == ActionLabel.CANDIDATE:
        weak_runs = 0
        note = f"Reconfirmed as candidate at {run_at.isoformat()}."
    elif action == ActionLabel.OBSERVE:
        weak_runs = 0
        note = f"Kept on watchlist at {run_at.isoformat()}."
    else:
        weak_runs += 1
        note = f"Weak run {weak_runs}/{max_weak_runs} at {run_at.isoformat()}."
        if weak_runs >= max_weak_runs:
            active = False
            note = f"Removed after {weak_runs} consecutive weak runs at {run_at.isoformat()}."
    entry.last_seen_at = run_at
    entry.last_action = action.value
    entry.consecutive_weak_runs = weak_runs
    entry.active = active
    entry.note = note
    return entry
