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
    opendart_api_key: str | None
    anthropic_api_key: str | None
    google_api_key: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    output_dir: Path
    log_dir: Path
    performance_dir: Path
    min_price_us: float
    min_price_kr: float
    min_avg_volume: int
    top_n_candidates: int
    candidate_min_final_score: int
    observe_min_final_score: int
    candidate_min_chart_score: int
    candidate_min_news_score: int
    short_term_buy_score: int
    short_term_watch_score: int
    mid_term_buy_score: int
    mid_term_watch_score: int
    max_news_age_hours: int
    universe_symbols: list[str]
    us_universe_symbols: list[str]
    kr_universe_symbols: list[str]
    us_universe_source: str
    universe_mode: str
    holdings_path: Path
    kr_flow_path: Path
    event_calendar_path: Path
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

    def min_price_for_market(self, market: str) -> float:
        return self.min_price_kr if market.upper() == "KR" else self.min_price_us


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


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
    input_dir = root / "data" / "inputs"
    log_dir = root / "data" / "logs"
    performance_dir = root / "data" / "performance"
    watchlist_path = output_dir / "watchlist.json"
    holdings_path = input_dir / "holdings.json"
    kr_flow_path = input_dir / "kr_flow_snapshot.json"
    event_calendar_path = input_dir / "event_calendar.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    performance_dir.mkdir(parents=True, exist_ok=True)
    llm_provider = (_env_value("LLM_PROVIDER") or "openai").lower()
    default_model = (
        _env_value("LLM_MODEL_DEFAULT")
        or _env_value("LLM_MODEL")
        or _env_value("OPENAI_MODEL")
        or _default_model_for_provider(llm_provider)
    )
    role_defaults = _default_role_models(llm_provider, default_model)
    return AppConfig(
        llm_provider=llm_provider,
        llm_model_default=default_model,
        llm_model_chart=_env_value("LLM_MODEL_CHART") or role_defaults["chart"],
        llm_model_news=_env_value("LLM_MODEL_NEWS") or role_defaults["news"],
        llm_model_final=_env_value("LLM_MODEL_FINAL") or role_defaults["final"],
        llm_model_macro=_env_value("LLM_MODEL_MACRO") or role_defaults["macro"],
        openai_api_key=_env_value("OPENAI_API_KEY"),
        opendart_api_key=_env_value("OPENDART_API_KEY"),
        anthropic_api_key=_env_value("ANTHROPIC_API_KEY"),
        google_api_key=_env_value("GOOGLE_API_KEY"),
        telegram_bot_token=_env_value("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env_value("TELEGRAM_CHAT_ID"),
        output_dir=output_dir,
        log_dir=log_dir,
        performance_dir=performance_dir,
        min_price_us=float(os.getenv("MIN_PRICE_US", os.getenv("MIN_PRICE", "10"))),
        min_price_kr=float(os.getenv("MIN_PRICE_KR", "5000")),
        min_avg_volume=int(os.getenv("MIN_AVG_VOLUME", "1000000")),
        top_n_candidates=int(os.getenv("TOP_N_CANDIDATES", "5")),
        candidate_min_final_score=int(os.getenv("CANDIDATE_MIN_FINAL_SCORE", "70")),
        observe_min_final_score=int(os.getenv("OBSERVE_MIN_FINAL_SCORE", "55")),
        candidate_min_chart_score=int(os.getenv("CANDIDATE_MIN_CHART_SCORE", "68")),
        candidate_min_news_score=int(os.getenv("CANDIDATE_MIN_NEWS_SCORE", "45")),
        short_term_buy_score=int(os.getenv("SHORT_TERM_BUY_SCORE", "70")),
        short_term_watch_score=int(os.getenv("SHORT_TERM_WATCH_SCORE", "55")),
        mid_term_buy_score=int(os.getenv("MID_TERM_BUY_SCORE", "70")),
        mid_term_watch_score=int(os.getenv("MID_TERM_WATCH_SCORE", "55")),
        max_news_age_hours=int(os.getenv("MAX_NEWS_AGE_HOURS", "72")),
        universe_symbols=_parse_universe(_env_value("STOCK_UNIVERSE")),
        us_universe_symbols=_parse_universe(_env_value("US_STOCK_UNIVERSE") or _env_value("STOCK_UNIVERSE")),
        kr_universe_symbols=_parse_kr_universe(_env_value("KR_STOCK_UNIVERSE")),
        us_universe_source=(_env_value("US_UNIVERSE_SOURCE") or "curated").lower(),
        universe_mode=(_env_value("UNIVERSE_MODE") or "discovery_plus_watchlist").lower(),
        holdings_path=Path(_env_value("HOLDINGS_PATH") or str(holdings_path)),
        kr_flow_path=Path(_env_value("KR_FLOW_PATH") or str(kr_flow_path)),
        event_calendar_path=Path(_env_value("EVENT_CALENDAR_PATH") or str(event_calendar_path)),
        watchlist_path=Path(_env_value("WATCHLIST_PATH") or str(watchlist_path)),
        include_watchlist=(os.getenv("INCLUDE_WATCHLIST", "true").strip().lower() in {"1", "true", "yes", "on"}),
        watchlist_max_weak_runs=int(os.getenv("WATCHLIST_MAX_WEAK_RUNS", "3")),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
    )
