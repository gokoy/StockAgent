from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from app.config import AppConfig

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class BaseLLMProvider(ABC):
    provider_name: str

    def __init__(self, config: AppConfig):
        self.config = config

    @abstractmethod
    def generate_structured(self, system_prompt: str, payload: dict, response_model: type[SchemaT]) -> SchemaT:
        raise NotImplementedError

    @staticmethod
    def payload_text(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=True)
