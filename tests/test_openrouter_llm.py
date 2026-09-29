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


def _fake_client(monkeypatch: pytest.MonkeyPatch, responses: list) -> list[dict]:
    """Instala un OpenAI falso que devuelve/lanza `responses` en orden y registra cada llamada."""
    calls: list[dict] = []

    def _create(**kw):
        calls.append(kw)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))

    import openai as openai_mod

    import agents.marketing_agents.llm as llm_mod

    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(llm_mod.time, "sleep", lambda _s: None)
    return calls


def _ok(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_openrouter_sends_fallback_models_capped_at_three(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_client(monkeypatch, [_ok('{"a": 1}')])
    client = OpenAILLM(
        "sk-or-test",
        model="m1:free",
        base_url="https://openrouter.ai/api/v1",
        fallback_models=["m2:free", "m3:free", "m4:free"],
        disable_reasoning=True,
    )
    assert client.complete_json("sys", "user") == {"a": 1}
    assert calls[0]["extra_body"] == {
        "models": ["m1:free", "m2:free", "m3:free"],
        "reasoning": {"enabled": False},
    }
    assert "response_format" not in calls[0]


def test_retries_on_empty_choices_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    empty = SimpleNamespace(choices=None, error={"code": 503, "message": "overloaded"})
    calls = _fake_client(monkeypatch, [empty, _ok("```json\n{\"hook\": \"hola\"}\n```")])
    client = OpenAILLM("sk-or-test", model="m1:free", base_url="https://openrouter.ai/api/v1")
    assert client.complete_json("sys", "user") == {"hook": "hola"}
    assert len(calls) == 2


def test_retries_on_429_and_raises_after_exhausting(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from openai import RateLimitError

    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    err = RateLimitError("rate limited", response=httpx.Response(429, request=req), body=None)
    calls = _fake_client(monkeypatch, [err, err, err])
    client = OpenAILLM(
        "sk-or-test", model="m1:free", base_url="https://openrouter.ai/api/v1", max_retries=3
    )
    with pytest.raises(RateLimitError):
        client.complete_json("sys", "user")
    assert len(calls) == 3


def test_parse_json_tolerates_surrounding_text() -> None:
    from agents.marketing_agents.llm import _parse_json

    assert _parse_json('Claro, aquí está:\n{"copy_final": "x"}\nSaludos') == {"copy_final": "x"}
