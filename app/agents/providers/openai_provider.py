from __future__ import annotations

from app.agents.providers.base import BaseLLMProvider, SchemaT


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"

    def __init__(self, config):
        super().__init__(config)
        from openai import OpenAI

        self._client = OpenAI(api_key=config.openai_api_key, timeout=config.llm_timeout_seconds)

    def generate_structured(
        self,
        system_prompt: str,
        payload: dict,
        response_model: type[SchemaT],
        model_name: str,
    ) -> SchemaT:
        schema = self.strict_json_schema(response_model)
        response = self._client.responses.create(
            model=model_name,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": self.payload_text(payload)}]},
            ],
            temperature=0,
            text={
                "format": {
                    "type": "json_schema",
                    "name": response_model.__name__,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("OpenAI response did not contain output_text")
        return response_model.model_validate_json(output_text)
