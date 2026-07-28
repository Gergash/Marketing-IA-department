"""Abstracción de LLM: Ollama, Anthropic y OpenAI con salida JSON parseada."""

from __future__ import annotations

import json
import re
from typing import Any


class OllamaLLM:
    """Cliente LLM local vía API HTTP de Ollama (`/api/chat` con salida JSON)."""

    def __init__(
        self,
        base_url: str,
        model: str = "llama3",
        *,
        keep_alive: str = "30m",
        timeout_seconds: int = 300,
    ) -> None:
        """Guarda URL base, modelo, ventana `keep_alive` y timeout tolerante a cold-start.

        Ollama descarga el modelo tras ~5 min inactivo; sin `keep_alive` la primera llamada
        de cada run vuelve a cargar ~5GB y supera el timeout, y los agentes caen al stub
        (texto de plantilla) sin error visible para el usuario.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._keep_alive = keep_alive
        self._timeout_seconds = timeout_seconds

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
        """Pide una respuesta JSON al modelo y la parsea como dict."""
        import httpx

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": system + "\n\nRespond ONLY with valid JSON. No markdown, no code fences.",
                },
                {"role": "user", "content": user},
            ],
            "format": "json",
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"num_predict": max_tokens},
        }
        resp = httpx.post(
            f"{self._base_url}/api/chat", json=payload, timeout=self._timeout_seconds
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return _parse_json(content)


class AnthropicLLM:
    """Cliente Messages API de Anthropic con respuesta forzada a JSON parseable."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        """Inicializa el cliente oficial `anthropic` con la clave y el modelo."""
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
        """Envía system+user y devuelve el primer bloque de texto como JSON."""
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
    """Cliente Chat Completions de OpenAI con `response_format` json_object."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        """Crea el cliente OpenAI con API key y modelo de chat."""
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
        """Obtiene un objeto JSON del asistente y lo parsea."""
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
    """Quita fences Markdown opcionales y decodifica JSON estricto."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    return json.loads(cleaned.strip())


def get_llm() -> OllamaLLM | AnthropicLLM | OpenAILLM | None:
    """Instancia el cliente según `LLM_PROVIDER` y claves en settings; `None` activa stubs en agentes."""
    from gateway.app.core.settings import get_settings
    s = get_settings()
    if s.llm_provider == "ollama":
        return OllamaLLM(
            s.ollama_base_url,
            s.ollama_model,
            keep_alive=s.ollama_keep_alive,
            timeout_seconds=s.llm_timeout_seconds,
        )
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        return AnthropicLLM(s.anthropic_api_key, s.llm_model)
    if s.llm_provider == "openai" and s.openai_api_key:
        return OpenAILLM(s.openai_api_key)
    return None
