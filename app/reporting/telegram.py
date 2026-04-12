from __future__ import annotations

import requests

from app.config import AppConfig


def send_telegram_message(message: str, config: AppConfig) -> bool:
    if not config.telegram_enabled:
        return False
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    for chunk in _split_message(message):
        response = requests.post(
            url,
            json={
                "chat_id": config.telegram_chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
                "parse_mode": "HTML",
            },
            timeout=20,
        )
        response.raise_for_status()
    return True


def send_telegram_test_message(config: AppConfig) -> bool:
    return send_telegram_message("StockAgent Telegram connectivity test", config)


def _split_message(message: str, max_length: int = 3800) -> list[str]:
    if len(message) <= max_length:
        return [message]

    chunks: list[str] = []
    current = ""
    for block in message.split("\n\n"):
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = block
    if current:
        chunks.append(current)
    return chunks
