from __future__ import annotations

from app.agents.providers.anthropic_provider import AnthropicProvider
from app.agents.providers.base import BaseLLMProvider
from app.agents.providers.gemini_provider import GeminiProvider
from app.agents.providers.openai_provider import OpenAIProvider
from app.config import AppConfig


def build_provider(config: AppConfig) -> BaseLLMProvider:
    provider = config.llm_provider.lower()
    if provider == "openai":
        if not config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        return OpenAIProvider(config)
    if provider == "anthropic":
        if not config.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        return AnthropicProvider(config)
    if provider == "gemini":
        if not config.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is not configured")
        return GeminiProvider(config)
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {config.llm_provider}")
