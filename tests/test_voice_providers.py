"""Pruebas de voice_providers.py: mock, ElevenLabs (monkeypatched), OpenAI TTS, fallos de proveedor."""

import pytest

from agents.marketing_agents.voice_providers import synthesize_voice
from gateway.app.core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_static_audio(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from agents.marketing_agents import voice_providers

    monkeypatch.setattr(voice_providers, "_STATIC_DIR", tmp_path / "audio")


def test_spanish_is_default_language() -> None:
    s = get_settings()
    assert s.voice_language == "es"
    assert s.elevenlabs_voice_id  # tiene un valor por defecto no vacío


def test_mock_provider_returns_audio_url_and_positive_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_PROVIDER", "mock")
    get_settings.cache_clear()

    url, duration = synthesize_voice("Hola, este es un texto de narración de prueba en español.")
    assert url.startswith("http://localhost:8000/static/audio/")
    assert duration > 0


def test_elevenlabs_happy_path_monkeypatched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-key")
    get_settings.cache_clear()

    class _FakeResponse:
        content = b"fake-mp3-bytes"

        def raise_for_status(self) -> None:
            return None

    def _fake_post(url, *, json, headers, timeout):
        assert "text-to-speech" in url
        assert headers["xi-api-key"] == "fake-key"
        return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", _fake_post)

    url, duration = synthesize_voice("Texto de prueba en español para ElevenLabs.")
    assert url.startswith("http://localhost:8000/static/audio/")
    assert duration > 0


def test_openai_tts_selected_via_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    get_settings.cache_clear()

    class _FakeSpeechResponse:
        def read(self) -> bytes:
            return b"fake-openai-audio-bytes"

    class _FakeAudio:
        class speech:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                assert kwargs["input"]
                return _FakeSpeechResponse()

    class _FakeOpenAIClient:
        def __init__(self, api_key: str) -> None:
            self.audio = _FakeAudio()

    import openai as openai_module

    monkeypatch.setattr(openai_module, "OpenAI", _FakeOpenAIClient)

    url, duration = synthesize_voice("Texto de prueba en español para OpenAI TTS.")
    assert url.startswith("http://localhost:8000/static/audio/")
    assert duration > 0


def test_elevenlabs_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="voice_synth_failed"):
        synthesize_voice("Texto sin API key configurada.")


def test_elevenlabs_api_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-key")
    get_settings.cache_clear()

    import httpx

    def _raise_post(*args, **kwargs):
        raise httpx.TimeoutException("boom")

    monkeypatch.setattr(httpx, "post", _raise_post)

    with pytest.raises(RuntimeError, match="voice_synth_failed"):
        synthesize_voice("Texto que dispara timeout.")
