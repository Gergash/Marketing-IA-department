from __future__ import annotations

import json
import re
from typing import Any


class AnthropicLLM:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
        import anthropic
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system + "\n\nRespond ONLY with valid JSON. No markdown, no code fences.",
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        return _parse_json(msg.content[0].text)


class OpenAILLM:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return _parse_json(resp.choices[0].message.content)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    return json.loads(cleaned.strip())


def get_llm() -> AnthropicLLM | OpenAILLM | None:
    """Return configured LLM client, or None to fall back to stub output."""
    from gateway.app.core.settings import get_settings
    s = get_settings()
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        return AnthropicLLM(s.anthropic_api_key, s.llm_model)
    if s.llm_provider == "openai" and s.openai_api_key:
        return OpenAILLM(s.openai_api_key)
    return None
