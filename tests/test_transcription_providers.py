"""Pruebas de transcription_providers.py: mock, whisper-1 (mockeado), chunking >25MB, fallos."""

from pathlib import Path

import pytest

from agents.marketing_agents import transcription_providers as tp
from gateway.app.core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_mock_provider_returns_deterministic_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "mock")
    get_settings.cache_clear()

    transcript = tp.transcribe_clip("clip1", Path("/fake/clip1.mp4"))
    assert transcript is not None
    assert transcript.clip_id == "clip1"
    assert len(transcript.words) > 0
    assert transcript.text


def test_clip_under_25mb_single_whisper_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    get_settings.cache_clear()

    calls = []
    monkeypatch.setattr(tp, "_extract_audio", lambda video_path: Path("/tmp/fake_audio.wav"))
    monkeypatch.setattr(tp, "_file_size_bytes", lambda path: 1024)  # muy por debajo de 25MB

    def _fake_whisper_call(audio_path, api_key, *, start_s=0.0, end_s=None):
        calls.append((start_s, end_s))
        return {
            "text": "hola mundo",
            "words": [
                {"word": "hola", "start": 0.0, "end": 0.4},
                {"word": "mundo", "start": 0.4, "end": 0.9},
            ],
        }

    monkeypatch.setattr(tp, "_whisper_call", _fake_whisper_call)

    transcript = tp.transcribe_clip("clip1", Path("/fake/clip1.mp4"))
    assert len(calls) == 1  # una sola llamada, sin chunking
    assert transcript.text == "hola mundo"
    assert [w.text for w in transcript.words] == ["hola", "mundo"]
    assert transcript.words[1].start_s == pytest.approx(0.4)


def test_clip_over_25mb_chunked_and_offset_corrected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    get_settings.cache_clear()

    monkeypatch.setattr(tp, "_extract_audio", lambda video_path: Path("/tmp/fake_audio.wav"))
    monkeypatch.setattr(tp, "_file_size_bytes", lambda path: 60 * 1024 * 1024)  # 60MB → 3 chunks
    monkeypatch.setattr(tp, "_probe_duration_seconds", lambda path: 90.0)  # 3 chunks de 30s

    def _fake_whisper_call(audio_path, api_key, *, start_s=0.0, end_s=None):
        # cada chunk transcribe una sola palabra a t=0.1s relativo al inicio del chunk
        return {
            "text": f"palabra_{int(start_s)}",
            "words": [{"word": f"palabra_{int(start_s)}", "start": 0.1, "end": 0.5}],
        }

    monkeypatch.setattr(tp, "_whisper_call", _fake_whisper_call)

    transcript = tp.transcribe_clip("clip1", Path("/fake/clip1.mp4"))
    assert len(transcript.words) == 3
    # offset-corrected: chunk 0 → ~0.1s, chunk 1 (start_s=30) → ~30.1s, chunk 2 (start_s=60) → ~60.1s
    starts = sorted(w.start_s for w in transcript.words)
    assert starts[0] == pytest.approx(0.1)
    assert starts[1] == pytest.approx(30.1)
    assert starts[2] == pytest.approx(60.1)


def test_word_at_chunk_boundary_not_duplicated_or_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Palabra justo en el borde de un chunk (offset-correction) no se duplica ni se pierde."""
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    get_settings.cache_clear()

    monkeypatch.setattr(tp, "_extract_audio", lambda video_path: Path("/tmp/fake_audio.wav"))
    monkeypatch.setattr(tp, "_file_size_bytes", lambda path: 50 * 1024 * 1024)  # 2 chunks
    monkeypatch.setattr(tp, "_probe_duration_seconds", lambda path: 40.0)  # 2 chunks de 20s

    def _fake_whisper_call(audio_path, api_key, *, start_s=0.0, end_s=None):
        if start_s == 0.0:
            # última palabra del primer chunk, muy cerca del borde (19.9s relativo)
            return {"text": "borde", "words": [{"word": "borde", "start": 19.9, "end": 20.0}]}
        # el segundo chunk no repite la palabra "borde"
        return {"text": "siguiente", "words": [{"word": "siguiente", "start": 0.0, "end": 0.3}]}

    monkeypatch.setattr(tp, "_whisper_call", _fake_whisper_call)

    transcript = tp.transcribe_clip("clip1", Path("/fake/clip1.mp4"))
    boundary_words = [w for w in transcript.words if w.text == "borde"]
    assert len(boundary_words) == 1
    assert boundary_words[0].start_s == pytest.approx(19.9)  # offset 0 (primer chunk)
    assert [w.text for w in transcript.words] == ["borde", "siguiente"]


def test_whisper_error_after_retries_clip_excluded_run_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    get_settings.cache_clear()

    monkeypatch.setattr(tp, "_file_size_bytes", lambda path: 1024)

    # clip1 siempre falla; clip2 tiene una ruta de audio distinguible por nombre
    def _extract_audio_side_effect(video_path):
        return Path(f"/tmp/{video_path.name}.wav")

    monkeypatch.setattr(tp, "_extract_audio", _extract_audio_side_effect)

    def _whisper_dispatch(audio_path, api_key, *, start_s=0.0, end_s=None):
        if "clip1" in str(audio_path):
            raise RuntimeError("whisper api error")
        return {"text": "ok", "words": [{"word": "ok", "start": 0.0, "end": 0.3}]}

    monkeypatch.setattr(tp, "_whisper_call", _whisper_dispatch)

    results = tp.transcribe_clips([
        ("clip1", Path("/fake/clip1.mp4")),
        ("clip2", Path("/fake/clip2.mp4")),
    ])
    assert len(results) == 1
    assert results[0].clip_id == "clip2"


def test_all_clips_fail_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    get_settings.cache_clear()

    monkeypatch.setattr(tp, "_extract_audio", lambda video_path: Path("/tmp/fake_audio.wav"))
    monkeypatch.setattr(tp, "_file_size_bytes", lambda path: 1024)

    def _always_fail(audio_path, api_key, *, start_s=0.0, end_s=None):
        raise RuntimeError("whisper api error")

    monkeypatch.setattr(tp, "_whisper_call", _always_fail)

    with pytest.raises(RuntimeError, match="transcription_failed"):
        tp.transcribe_clips([
            ("clip1", Path("/fake/clip1.mp4")),
            ("clip2", Path("/fake/clip2.mp4")),
        ])


def test_empty_transcript_silent_clip_stays_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    get_settings.cache_clear()

    monkeypatch.setattr(tp, "_extract_audio", lambda video_path: Path("/tmp/fake_audio.wav"))
    monkeypatch.setattr(tp, "_file_size_bytes", lambda path: 1024)
    monkeypatch.setattr(tp, "_whisper_call", lambda *a, **k: {"text": "", "words": []})

    transcript = tp.transcribe_clip("clip_silent", Path("/fake/silent.mp4"))
    assert transcript is not None
    assert transcript.words == []
    assert transcript.text == ""
