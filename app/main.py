from __future__ import annotations

import argparse
import importlib.util

from pydantic import BaseModel

from app.agents.llm_client import LLMClient
from app.config import LLM_ROLES, load_config
from app.orchestrator import run_scan
from app.reporting.telegram import send_telegram_test_message


class SmokeResponse(BaseModel):
    ok: bool
    provider: str
    reason: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="StockAgent swing scan")
    parser.add_argument("--telegram-test", action="store_true", help="Send a Telegram connectivity test message")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram delivery")
    parser.add_argument("--self-check", action="store_true", help="Print local configuration and dependency status")
    parser.add_argument("--llm-smoke", action="store_true", help="Run a minimal structured output smoke test")
    parser.add_argument("--llm-role", default="default", choices=LLM_ROLES, help="Role to use for the LLM smoke test")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of symbols processed")
    parser.add_argument("--timezone", default="Asia/Seoul", help="Timezone name for run timestamps")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config()
    if args.self_check:
        print(run_self_check(config))
        return 0
    if args.telegram_test:
        ok = send_telegram_test_message(config)
        print("telegram_test_sent" if ok else "telegram_not_configured")
        return 0
    if args.llm_smoke:
        print(run_llm_smoke(config, role=args.llm_role))
        return 0
    result, message = run_scan(
        config,
        timezone_name=args.timezone,
        send_telegram=not args.no_telegram,
        max_stocks=args.limit,
    )
    print(message)
    print(f"candidate_count={result.candidate_count}")
    return 0


def run_self_check(config) -> str:
    provider_package = {
        "openai": "openai",
        "anthropic": "anthropic",
        "gemini": "google.genai",
    }.get(config.llm_provider, "unknown")
    package_found = importlib.util.find_spec(provider_package) is not None if provider_package != "unknown" else False
    lines = [
        f"llm_provider={config.llm_provider}",
        f"llm_model_default={config.llm_model_default}",
        f"llm_model_chart={config.llm_model_chart}",
        f"llm_model_news={config.llm_model_news}",
        f"llm_model_final={config.llm_model_final}",
        f"llm_model_macro={config.llm_model_macro}",
        f"candidate_min_final_score={config.candidate_min_final_score}",
        f"observe_min_final_score={config.observe_min_final_score}",
        f"candidate_min_chart_score={config.candidate_min_chart_score}",
        f"candidate_min_news_score={config.candidate_min_news_score}",
        f"llm_enabled={config.llm_enabled}",
        f"provider_package={provider_package}",
        f"provider_package_found={package_found}",
        f"telegram_enabled={config.telegram_enabled}",
        f"universe_size={len(config.universe_symbols)}",
    ]
    return "\n".join(lines)


def run_llm_smoke(config, role: str = "default") -> str:
    if not config.llm_enabled:
        return "llm_not_configured"
    client = LLMClient(config)
    result = client.generate_structured(
        system_prompt="Return a minimal JSON object confirming the provider.",
        payload={"provider": config.llm_provider, "role": role, "model": config.model_for_role(role)},
        response_model=SmokeResponse,
        role=role,
    )
    return result.model_dump_json()


if __name__ == "__main__":
    raise SystemExit(main())
