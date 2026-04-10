from __future__ import annotations

import copy
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
    def generate_structured(
        self,
        system_prompt: str,
        payload: dict,
        response_model: type[SchemaT],
        model_name: str,
    ) -> SchemaT:
        raise NotImplementedError

    @staticmethod
    def payload_text(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=True)

    @staticmethod
    def strict_json_schema(response_model: type[SchemaT]) -> dict:
        schema = copy.deepcopy(response_model.model_json_schema())
        BaseLLMProvider._normalize_schema(schema)
        return schema

    @staticmethod
    def _normalize_schema(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
            for value in node.values():
                BaseLLMProvider._normalize_schema(value)
        elif isinstance(node, list):
            for item in node:
                BaseLLMProvider._normalize_schema(item)
