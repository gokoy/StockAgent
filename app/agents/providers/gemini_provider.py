from __future__ import annotations

from app.agents.providers.base import BaseLLMProvider, SchemaT


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(self, config):
        super().__init__(config)
        from google import genai

        self._client = genai.Client(api_key=config.google_api_key)

    def generate_structured(self, system_prompt: str, payload: dict, response_model: type[SchemaT]) -> SchemaT:
        response = self._client.models.generate_content(
            model=self.config.llm_model,
            contents=f"{system_prompt}\n\n{self.payload_text(payload)}",
            config={
                "temperature": 0,
                "response_mime_type": "application/json",
                "response_json_schema": response_model.model_json_schema(),
            },
        )
        response_text = getattr(response, "text", None)
        if not response_text:
            raise RuntimeError("Gemini response did not contain text")
        return response_model.model_validate_json(response_text)
