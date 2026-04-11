from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


LLM_ROLES = ("default", "chart", "news", "final", "macro")


@dataclass(frozen=True)
class AppConfig:
    llm_provider: str
    llm_model_default: str
    llm_model_chart: str
    llm_model_news: str
    llm_model_final: str
    llm_model_macro: str
    openai_api_key: str | None
    anthropic_api_key: str | None
    google_api_key: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    output_dir: Path
    log_dir: Path
    performance_dir: Path
    min_price: float
    min_avg_volume: int
    top_n_candidates: int
    candidate_min_final_score: int
    observe_min_final_score: int
    candidate_min_chart_score: int
    candidate_min_news_score: int
    max_news_age_hours: int
    universe_symbols: list[str]
    us_universe_symbols: list[str]
    kr_universe_symbols: list[str]
    universe_mode: str
    watchlist_path: Path
    include_watchlist: bool
    watchlist_max_weak_runs: int
    llm_timeout_seconds: int

    @property
    def llm_enabled(self) -> bool:
        return bool(self.provider_api_key)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def provider_api_key(self) -> str | None:
        provider = self.llm_provider.lower()
        if provider == "openai":
            return self.openai_api_key
        if provider == "anthropic":
            return self.anthropic_api_key
        if provider == "gemini":
            return self.google_api_key
        return None

    def model_for_role(self, role: str) -> str:
        normalized = role.strip().lower()
        if normalized == "chart":
            return self.llm_model_chart
        if normalized == "news":
            return self.llm_model_news
        if normalized == "final":
            return self.llm_model_final
        if normalized == "macro":
            return self.llm_model_macro
        return self.llm_model_default


def _parse_universe(raw: str | None) -> list[str]:
    if raw:
        return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]
    return [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "META",
        "GOOGL",
        "TSLA",
        "AVGO",
        "AMD",
        "UBER",
        "PLTR",
        "NFLX",
    ]


def _parse_kr_universe(raw: str | None) -> list[str]:
    if raw:
        return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]
    return [
        "005930.KS",
        "000660.KS",
        "035420.KS",
        "051910.KS",
        "005380.KS",
        "035720.KS",
    ]


def _default_model_for_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized == "anthropic":
        return "claude-3-5-sonnet-latest"
    if normalized == "gemini":
        return "gemini-2.5-flash"
    return "gpt-4.1-mini"


def _default_role_models(provider: str, default_model: str) -> dict[str, str]:
    normalized = provider.strip().lower()
    if normalized == "openai":
        return {
            "chart": default_model,
            "news": default_model,
            "final": "gpt-4.1",
            "macro": default_model,
        }
    if normalized == "anthropic":
        return {
            "chart": default_model,
            "news": default_model,
            "final": default_model,
            "macro": default_model,
        }
    if normalized == "gemini":
        return {
            "chart": default_model,
            "news": default_model,
            "final": default_model,
            "macro": default_model,
        }
    return {
        "chart": default_model,
        "news": default_model,
        "final": default_model,
        "macro": default_model,
    }


def load_config() -> AppConfig:
    root = Path(__file__).resolve().parent.parent
    output_dir = root / "data" / "outputs"
    log_dir = root / "data" / "logs"
    performance_dir = root / "data" / "performance"
    watchlist_path = output_dir / "watchlist.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    performance_dir.mkdir(parents=True, exist_ok=True)
    llm_provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    default_model = os.getenv(
        "LLM_MODEL_DEFAULT",
        os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", _default_model_for_provider(llm_provider))),
    )
    role_defaults = _default_role_models(llm_provider, default_model)
    return AppConfig(
        llm_provider=llm_provider,
        llm_model_default=default_model,
        llm_model_chart=os.getenv("LLM_MODEL_CHART", role_defaults["chart"]),
        llm_model_news=os.getenv("LLM_MODEL_NEWS", role_defaults["news"]),
        llm_model_final=os.getenv("LLM_MODEL_FINAL", role_defaults["final"]),
        llm_model_macro=os.getenv("LLM_MODEL_MACRO", role_defaults["macro"]),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        output_dir=output_dir,
        log_dir=log_dir,
        performance_dir=performance_dir,
        min_price=float(os.getenv("MIN_PRICE", "10")),
        min_avg_volume=int(os.getenv("MIN_AVG_VOLUME", "1000000")),
        top_n_candidates=int(os.getenv("TOP_N_CANDIDATES", "5")),
        candidate_min_final_score=int(os.getenv("CANDIDATE_MIN_FINAL_SCORE", "70")),
        observe_min_final_score=int(os.getenv("OBSERVE_MIN_FINAL_SCORE", "55")),
        candidate_min_chart_score=int(os.getenv("CANDIDATE_MIN_CHART_SCORE", "68")),
        candidate_min_news_score=int(os.getenv("CANDIDATE_MIN_NEWS_SCORE", "45")),
        max_news_age_hours=int(os.getenv("MAX_NEWS_AGE_HOURS", "72")),
        universe_symbols=_parse_universe(os.getenv("STOCK_UNIVERSE")),
        us_universe_symbols=_parse_universe(os.getenv("US_STOCK_UNIVERSE", os.getenv("STOCK_UNIVERSE"))),
        kr_universe_symbols=_parse_kr_universe(os.getenv("KR_STOCK_UNIVERSE")),
        universe_mode=os.getenv("UNIVERSE_MODE", "discovery_plus_watchlist").strip().lower(),
        watchlist_path=Path(os.getenv("WATCHLIST_PATH", str(watchlist_path))),
        include_watchlist=os.getenv("INCLUDE_WATCHLIST", "true").strip().lower() in {"1", "true", "yes", "on"},
        watchlist_max_weak_runs=int(os.getenv("WATCHLIST_MAX_WEAK_RUNS", "3")),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
    )
