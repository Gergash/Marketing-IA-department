"""Pruebas del fix de cold-start de Ollama: keep_alive en el payload y timeout configurable.

Contexto: `get_llm()` devuelve un OllamaLLM aunque Ollama esté frío; la primera llamada
carga ~5GB y superaba el timeout de 180s → los agentes caían al stub y el copy salía
genérico sin error visible. keep_alive evita la descarga entre runs.
"""

import pytest

from agents.marketing_agents.llm import OllamaLLM


class _FakeResponse:
    def __init__(self, content: str = '{"ok": true}') -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"message": {"content": self._content}}


@pytest.fixture
def captured_post(monkeypatch: pytest.MonkeyPatch):
    """Intercepta httpx.post y devuelve los kwargs con que fue llamado."""
    import httpx

    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)
    return captured


def test_payload_includes_keep_alive(captured_post) -> None:
    llm = OllamaLLM("http://localhost:11434", "llama3.1", keep_alive="30m")

    llm.complete_json("system", "user")

    assert captured_post["json"]["keep_alive"] == "30m"


def test_keep_alive_is_configurable(captured_post) -> None:
    llm = OllamaLLM("http://localhost:11434", "llama3.1", keep_alive="2h")

    llm.complete_json("system", "user")

    assert captured_post["json"]["keep_alive"] == "2h"


def test_timeout_tolerates_cold_start(captured_post) -> None:
    """180s no alcanzaba para cargar el modelo en frío; el default debe ser mayor."""
    llm = OllamaLLM("http://localhost:11434", "llama3.1")

    llm.complete_json("system", "user")

    assert captured_post["timeout"] >= 300


def test_timeout_is_configurable(captured_post) -> None:
    llm = OllamaLLM("http://localhost:11434", "llama3.1", timeout_seconds=600)

    llm.complete_json("system", "user")

    assert captured_post["timeout"] == 600


def test_get_llm_wires_settings_into_ollama_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.app.core.settings import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "45m")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "420")
    get_settings.cache_clear()

    from agents.marketing_agents.llm import get_llm

    llm = get_llm()

    assert isinstance(llm, OllamaLLM)
    assert llm._keep_alive == "45m"
    assert llm._timeout_seconds == 420
