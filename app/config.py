from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    openai_model: str
    output_dir: Path
    log_dir: Path
    performance_dir: Path
    min_price: float
    min_avg_volume: int
    top_n_candidates: int
    max_news_age_hours: int
    universe_symbols: list[str]
    llm_timeout_seconds: int

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


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


def load_config() -> AppConfig:
    root = Path(__file__).resolve().parent.parent
    output_dir = root / "data" / "outputs"
    log_dir = root / "data" / "logs"
    performance_dir = root / "data" / "performance"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    performance_dir.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        output_dir=output_dir,
        log_dir=log_dir,
        performance_dir=performance_dir,
        min_price=float(os.getenv("MIN_PRICE", "10")),
        min_avg_volume=int(os.getenv("MIN_AVG_VOLUME", "1000000")),
        top_n_candidates=int(os.getenv("TOP_N_CANDIDATES", "5")),
        max_news_age_hours=int(os.getenv("MAX_NEWS_AGE_HOURS", "72")),
        universe_symbols=_parse_universe(os.getenv("STOCK_UNIVERSE")),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
    )
