from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.web.dashboard_data import MACRO_HISTORY_PATH, SECTOR_HISTORY_PATH, SNAPSHOT_PATH, refresh_dashboard_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the web dashboard data snapshot.")
    parser.add_argument(
        "--output",
        type=Path,
        default=SNAPSHOT_PATH,
        help="Snapshot JSON path. Defaults to data/web/dashboard_snapshot.json.",
    )
    parser.add_argument(
        "--macro-history-output",
        type=Path,
        default=MACRO_HISTORY_PATH,
        help="Macro history JSON path. Defaults to data/history/macro_history.json.",
    )
    parser.add_argument(
        "--sector-history-output",
        type=Path,
        default=SECTOR_HISTORY_PATH,
        help="Sector history JSON path. Defaults to data/history/sector_history.json.",
    )
    args = parser.parse_args()

    snapshot = refresh_dashboard_snapshot(
        args.output,
        macro_history_path=args.macro_history_output,
        sector_history_path=args.sector_history_output,
    )
    macro_count = sum(len(items) for items in snapshot["macro"]["groups"].values())
    sector_count = sum(len(snapshot["sectors"][market]["sectors"]) for market in ("US", "KR"))
    print(f"generated_at={snapshot['generated_at']}")
    print(f"macro_indicators={macro_count}")
    print(f"sectors={sector_count}")
    print(f"output={args.output}")
    print(f"macro_history_output={args.macro_history_output}")
    print(f"sector_history_output={args.sector_history_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
