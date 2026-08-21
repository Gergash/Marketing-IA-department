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

    def complete_text(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        """Respuesta de texto libre (chat asesor)."""
        import httpx

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"num_predict": max_tokens},
        }
        resp = httpx.post(
            f"{self._base_url}/api/chat", json=payload, timeout=self._timeout_seconds
        )
        resp.raise_for_status()
        return str(resp.json()["message"]["content"] or "").strip()


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

    def complete_text(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        """Respuesta de texto libre (chat asesor)."""
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return str(msg.content[0].text or "").strip()


class OpenAILLM:
    """Cliente Chat Completions compatible con OpenAI (API oficial u OpenRouter)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        *,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        """Crea el cliente OpenAI; `base_url` apunta a OpenRouter u otro proxy compatible."""
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        if default_headers:
            kwargs["default_headers"] = default_headers
        self._client = OpenAI(**kwargs)
        self._model = model
        self._base_url = (base_url or "").rstrip("/")

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
        """Obtiene un objeto JSON del asistente y lo parsea."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": system + "\n\nRespond ONLY with valid JSON. No markdown, no code fences.",
                },
                {"role": "user", "content": user},
            ],
        }
        # Algunos modelos vía OpenRouter no soportan response_format=json_object.
        if not self._base_url or "openrouter.ai" not in self._base_url:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception:
            if "response_format" in kwargs:
                kwargs.pop("response_format", None)
                resp = self._client.chat.completions.create(**kwargs)
            else:
                raise
        return _parse_json(resp.choices[0].message.content)

    def complete_text(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        """Respuesta de texto libre (chat asesor)."""
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return str(resp.choices[0].message.content or "").strip()


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
        base = (s.openai_api_base or "").strip() or None
        model = (s.openai_model or "").strip() or "gpt-4o-mini"
        headers: dict[str, str] | None = None
        if base and "openrouter.ai" in base:
            # OpenRouter recomienda estos headers para ranking/attribution de apps.
            referer = (s.openrouter_http_referer or s.public_image_base_url or "").strip()
            title = (s.openrouter_app_title or "Marketing DEPA IA").strip()
            headers = {}
            if referer:
                headers["HTTP-Referer"] = referer
            if title:
                headers["X-Title"] = title
        return OpenAILLM(
            s.openai_api_key,
            model=model,
            base_url=base,
            default_headers=headers or None,
        )
    return None
