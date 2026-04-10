from __future__ import annotations

import requests

from app.config import AppConfig


def send_telegram_message(message: str, config: AppConfig) -> bool:
    if not config.telegram_enabled:
        return False
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": config.telegram_chat_id, "text": message, "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()
    return True


def send_telegram_test_message(config: AppConfig) -> bool:
    return send_telegram_message("StockAgent Telegram connectivity test", config)
