from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from app.config import AppConfig

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self._client = None
        if config.openai_api_key:
            from openai import OpenAI

            self._client = OpenAI(api_key=config.openai_api_key, timeout=config.llm_timeout_seconds)

    def generate_structured(self, system_prompt: str, payload: dict, response_model: type[SchemaT]) -> SchemaT:
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        response = self._client.responses.create(
            model=self.config.openai_model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=True)}]},
            ],
            temperature=0,
            text={
                "format": {
                    "type": "json_schema",
                    "name": response_model.__name__,
                    "schema": response_model.model_json_schema(),
                    "strict": True,
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("OpenAI response did not contain output_text")
        return response_model.model_validate_json(output_text)
