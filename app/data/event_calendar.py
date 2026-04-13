from __future__ import annotations

import json
from pathlib import Path


def load_event_calendar(path: Path, market: str) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = payload.get(market.upper(), [])
    if not isinstance(items, list):
        return []
    results: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date", "")).strip()
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        results.append(f"{date} {title}".strip())
    return results
