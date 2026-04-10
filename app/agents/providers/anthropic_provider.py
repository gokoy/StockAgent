from __future__ import annotations

import json

from app.agents.providers.base import BaseLLMProvider, SchemaT


class AnthropicProvider(BaseLLMProvider):
    provider_name = "anthropic"

    def __init__(self, config):
        super().__init__(config)
        from anthropic import Anthropic

        self._client = Anthropic(api_key=config.anthropic_api_key, timeout=config.llm_timeout_seconds)

    def generate_structured(self, system_prompt: str, payload: dict, response_model: type[SchemaT]) -> SchemaT:
        response = self._client.messages.create(
            model=self.config.llm_model,
            max_tokens=1600,
            temperature=0,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": self.payload_text(
                        {
                            "task_payload": payload,
                            "json_schema": response_model.model_json_schema(),
                            "instruction": "Return only valid JSON that matches the schema exactly.",
                        }
                    ),
                }
            ],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": response_model.model_json_schema(),
                }
            },
        )
        output_text = _extract_anthropic_json(response.content)
        return response_model.model_validate_json(output_text)


def _extract_anthropic_json(blocks) -> str:
    for block in blocks:
        if isinstance(block, dict):
            if block.get("json") is not None:
                return json.dumps(block["json"])
            if block.get("text"):
                return block["text"]
        json_value = getattr(block, "json", None)
        if json_value is not None:
            return json.dumps(json_value)
        text_value = getattr(block, "text", None)
        if text_value:
            return text_value
    raise RuntimeError("Anthropic response did not contain a JSON block")
