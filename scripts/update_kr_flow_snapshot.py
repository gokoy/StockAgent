from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

try:
    from pykrx import stock as krx_stock
except Exception:  # pragma: no cover - optional dependency
    krx_stock = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update Korean market investor flow snapshot")
    parser.add_argument("--output", default="data/inputs/kr_flow_snapshot.json", help="Output JSON path")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="As-of date in YYYY-MM-DD")
    parser.add_argument("--source", choices=("auto", "manual", "pykrx"), default="auto", help="Snapshot source")
    parser.add_argument("--print-template", action="store_true", help="Print a manual snapshot template and exit")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.print_template:
        print(json.dumps(_manual_payload(args.date), ensure_ascii=False, indent=2))
        return 0

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, dict[str, str]] | None = None
    if args.source in {"auto", "pykrx"}:
        payload = _pykrx_payload(args.date)
        if payload:
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"kr_flow_snapshot_written source=pykrx path={output_path}")
            return 0
        if args.source == "pykrx":
            print("kr_flow_snapshot_failed source=pykrx")
            return 1

    payload = _manual_payload(args.date)
    if not _has_values(payload):
        print("kr_flow_snapshot_skipped no_manual_values")
        return 1
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"kr_flow_snapshot_written source=manual path={output_path}")
    return 0


def _pykrx_payload(as_of_date: str) -> dict[str, dict[str, str]] | None:
    if krx_stock is None:
        return None
    date_compact = as_of_date.replace("-", "")
    payload: dict[str, dict[str, str]] = {}
    for market in ("KOSPI", "KOSDAQ"):
        try:
            fn = getattr(krx_stock, "get_market_trading_value_by_investor", None)
            if fn is None:
                return None
            frame = fn(date_compact, date_compact, market=market)
            if frame.empty:
                continue
            latest = frame.iloc[-1]
            payload[market] = {
                "as_of": as_of_date,
                "foreign": _signed_korean_amount(float(latest.get("외국인합계", 0.0))),
                "institution": _signed_korean_amount(float(latest.get("기관합계", 0.0))),
                "individual": _signed_korean_amount(float(latest.get("개인", 0.0))),
            }
        except Exception:
            continue
    return payload or None


def _manual_payload(as_of_date: str) -> dict[str, dict[str, str]]:
    return {
        "KOSPI": {
            "as_of": as_of_date,
            "foreign": os.getenv("KR_FLOW_KOSPI_FOREIGN", "").strip(),
            "institution": os.getenv("KR_FLOW_KOSPI_INSTITUTION", "").strip(),
            "individual": os.getenv("KR_FLOW_KOSPI_INDIVIDUAL", "").strip(),
        },
        "KOSDAQ": {
            "as_of": as_of_date,
            "foreign": os.getenv("KR_FLOW_KOSDAQ_FOREIGN", "").strip(),
            "institution": os.getenv("KR_FLOW_KOSDAQ_INSTITUTION", "").strip(),
            "individual": os.getenv("KR_FLOW_KOSDAQ_INDIVIDUAL", "").strip(),
        },
    }


def _has_values(payload: dict[str, dict[str, str]]) -> bool:
    for market in ("KOSPI", "KOSDAQ"):
        item = payload.get(market, {})
        if any(str(item.get(key, "")).strip() for key in ("foreign", "institution", "individual")):
            return True
    return False


def _signed_korean_amount(value: float) -> str:
    amount = value / 100_000_000
    return f"{amount:+,.0f}억"


if __name__ == "__main__":
    raise SystemExit(main())
