from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import RunResult


def load_latest_result(output_dir: Path) -> RunResult | None:
    latest = output_dir / "latest.json"
    if not latest.exists():
        return None
    try:
        return RunResult.model_validate_json(latest.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_run_result(run_result: RunResult, output_dir: Path) -> Path:
    stamp = run_result.run_at.strftime("%Y%m%d_%H%M%S")
    target = output_dir / f"scan_{stamp}.json"
    latest = output_dir / "latest.json"
    payload = run_result.model_dump(mode="json")
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
