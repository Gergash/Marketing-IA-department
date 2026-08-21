"""OpenAI-compatible LLM: base_url (OpenRouter) + modelo desde settings."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.marketing_agents.llm import OpenAILLM, get_llm


def test_openai_llm_passes_base_url_to_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content='{"a":1}'))]
                    )
                )
            )

    import openai as openai_mod

    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAI)

    client = OpenAILLM(
        "sk-or-test",
        model="google/gemini-2.0-flash-001",
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": "https://example.com", "X-Title": "DEPA"},
    )
    assert captured["api_key"] == "sk-or-test"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["default_headers"]["X-Title"] == "DEPA"
    assert client._model == "google/gemini-2.0-flash-001"
    assert client.complete_json("sys", "user") == {"a": 1}


def test_get_llm_wires_openrouter_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.app.core.settings import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-v1-fake")
    monkeypatch.setenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENAI_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://marketing.example")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "Marketing DEPA IA")
    get_settings.cache_clear()

    import openai as openai_mod

    captured: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAI)

    client = get_llm()
    assert isinstance(client, OpenAILLM)
    assert client._model == "deepseek/deepseek-chat"
    assert client._base_url == "https://openrouter.ai/api/v1"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["default_headers"]["HTTP-Referer"] == "https://marketing.example"
    get_settings.cache_clear()
