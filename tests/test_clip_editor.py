"""Pruebas de ClipEditorAgent: seleccion hook-scored de segmentos entre clips transcritos."""

import pytest

from agents.marketing_agents.clip_editor import ClipEditorAgent
from agents.marketing_agents.schemas import BriefInput, StrategyOutput
from agents.marketing_agents.transcription_providers import ClipTranscript, Word


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fuerza fallback al stub deterministico (sin red).
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")


def _brief() -> BriefInput:
    return BriefInput(
        tema="automatizacion de marketing",
        publico_objetivo="dueños de negocio",
        red_social="instagram",
        objetivo="branding",
    )


def _strategy() -> StrategyOutput:
    return StrategyOutput(
        tipo_post="educativo",
        hook="¿Sabias que la IA puede ahorrarte horas de trabajo cada semana?",
        mensaje_base="Automatiza tu contenido de marketing con agentes de IA.",
        hashtags=["#IA"],
    )


def _transcript(clip_id: str, *, start: float, span_s: float, text: str) -> ClipTranscript:
    """Construye un transcript cuyo span de palabras cubre exactamente [start, start+span_s]."""
    words = [
        Word(text=w, start_s=start + i * (span_s / max(1, len(text.split()))),
             end_s=start + (i + 1) * (span_s / max(1, len(text.split()))))
        for i, w in enumerate(text.split())
    ]
    return ClipTranscript(clip_id=clip_id, words=words, text=text)


def test_selects_ordered_segments_across_clips_within_band() -> None:
    transcripts = [
        _transcript("clip1", start=0.0, span_s=30.0, text="¿Sabias que esto puede cambiar todo hoy mismo?"),
        _transcript("clip2", start=0.0, span_s=30.0, text="Muchos equipos pierden horas cada semana"),
        _transcript("clip3", start=0.0, span_s=30.0, text="Automatiza tu proceso de principio a fin"),
    ]

    segments = ClipEditorAgent().run(transcripts, _brief(), _strategy())

    assert len(segments) >= 1
    clip_ids_seen = [seg.clip_id for seg in segments]
    assert clip_ids_seen == sorted(clip_ids_seen, key=lambda cid: ["clip1", "clip2", "clip3"].index(cid))
    total_duration = sum(seg.end_s - seg.start_s for seg in segments)
    assert 6.0 <= total_duration <= 60.0
    assert sum(1 for seg in segments if seg.is_hook) == 1


def test_insufficient_total_footage_raises_clear_error() -> None:
    transcripts = [
        _transcript("clip1", start=0.0, span_s=2.0, text="hola mundo"),
        _transcript("clip2", start=0.0, span_s=1.5, text="solo esto"),
    ]

    with pytest.raises(RuntimeError, match="insufficient footage"):
        ClipEditorAgent().run(transcripts, _brief(), _strategy())


def test_malformed_llm_output_falls_back_to_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    import agents.marketing_agents.clip_editor as clip_editor_module

    class _BrokenLLM:
        def complete_json(self, system, user):
            return {"not_segments": "malformed"}

    monkeypatch.setattr(clip_editor_module, "get_llm", lambda: _BrokenLLM())

    transcripts = [
        _transcript("clip1", start=0.0, span_s=30.0, text="¿Sabias que esto puede cambiar todo hoy mismo?"),
    ]

    segments = ClipEditorAgent().run(transcripts, _brief(), _strategy())

    assert len(segments) == 1
    assert segments[0].clip_id == "clip1"
    assert sum(1 for seg in segments if seg.is_hook) == 1


def test_stub_selection_is_deterministic_given_same_input() -> None:
    transcripts = [
        _transcript("clip1", start=0.0, span_s=10.0, text="¿Sabias que esto funciona?"),
    ]

    agent = ClipEditorAgent()
    first = agent.run(transcripts, _brief(), _strategy())
    second = agent.run(transcripts, _brief(), _strategy())

    assert [s.model_dump() for s in first] == [s.model_dump() for s in second]
    assert first[0].is_hook is True
