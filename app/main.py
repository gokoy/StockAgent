from __future__ import annotations

import argparse

from app.config import load_config
from app.orchestrator import run_scan
from app.reporting.telegram import send_telegram_test_message


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="StockAgent swing scan")
    parser.add_argument("--telegram-test", action="store_true", help="Send a Telegram connectivity test message")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram delivery")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config()
    if args.telegram_test:
        ok = send_telegram_test_message(config)
        print("telegram_test_sent" if ok else "telegram_not_configured")
        return 0
    result, message = run_scan(config, send_telegram=not args.no_telegram)
    print(message)
    print(f"candidate_count={result.candidate_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
