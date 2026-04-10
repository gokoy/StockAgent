from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.agents.provider_factory import build_provider
from app.config import AppConfig

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self._provider = build_provider(config)

    def generate_structured(
        self,
        system_prompt: str,
        payload: dict,
        response_model: type[SchemaT],
        role: str = "default",
    ) -> SchemaT:
        model_name = self.config.model_for_role(role)
        return self._provider.generate_structured(system_prompt, payload, response_model, model_name)

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name
