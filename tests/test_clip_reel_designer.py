"""Pruebas ClipReelDesigner cloud: propose sin máster local + render con shorts."""

import pytest

from agents.marketing_agents.clip_reel_designer import ClipReelDesigner
from agents.marketing_agents.schemas import (
    BriefInput,
    CloudFootageRef,
    CopyOutput,
    StrategyOutput,
    TakeProposal,
)
from agents.marketing_agents.transcription_providers import ClipTranscript, Word
from agents.marketing_agents.video_producer import VideoProducerAgent


@pytest.fixture(autouse=True)
def _mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_PROVIDER", "mock")
    monkeypatch.setenv("STT_PROVIDER", "mock")
    monkeypatch.setenv("EFFECTS_ENABLED", "false")


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
        hook="¿Sabias que la IA puede ahorrarte horas?",
        mensaje_base="Automatiza tu contenido de marketing con agentes de IA.",
        hashtags=["#IA"],
    )


def _copy() -> CopyOutput:
    return CopyOutput(
        copy_final="Automatiza tu marketing con IA.",
        hashtags=["#IA"],
        cta="Escribe DEMO.",
        headline_for_image="Automatiza tu marketing",
        subline_for_image="Recupera tu tiempo",
    )


def _long_transcript(clip_id: str = "clip1") -> ClipTranscript:
    words = []
    texts = []
    # ~40s de palabras espaciadas para que el stub pueda elegir ventanas
    for i in range(80):
        start = i * 0.5
        end = start + 0.4
        w = "precio" if i % 10 == 0 else ("ubicacion" if i % 7 == 0 else f"palabra{i}")
        words.append(Word(text=w, start_s=start, end_s=end))
        texts.append(w)
    return ClipTranscript(clip_id=clip_id, words=words, text=" ".join(texts))


class _FakeProducer:
    def __init__(self, takes: list[TakeProposal]) -> None:
        self._takes = takes

    def run(self, *a, **kw) -> list[TakeProposal]:
        return self._takes


def test_propose_does_not_download_master_mp4(monkeypatch: pytest.MonkeyPatch) -> None:
    import agents.marketing_agents.clip_reel_designer as designer_module

    footage = [
        CloudFootageRef(file_id="file1", name="a.mp4", mime_type="video/mp4", clip_id="clip1"),
    ]
    monkeypatch.setattr(designer_module, "list_cloud_footage", lambda *a, **k: footage)
    monkeypatch.setattr(designer_module, "get_drive_access_token", lambda *a, **k: "token")
    monkeypatch.setattr(
        designer_module,
        "transcribe_cloud_footage",
        lambda *a, **k: [_long_transcript("clip1")],
    )

    def _no_render(*a, **k):
        raise AssertionError("propose must not call render_video")

    monkeypatch.setattr(designer_module, "render_video", _no_render)

    takes = [
        TakeProposal(
            id="take-1",
            clip_id="clip1",
            drive_file_id="file1",
            trim_in=0.0,
            trim_out=20.0,
            duration_s=20.0,
            transcript="precio oferta",
            is_hook=True,
            status="proposed",
            order=0,
        )
    ]
    out = ClipReelDesigner(producer_agent=_FakeProducer(takes)).propose(
        _brief(),
        _copy(),
        _strategy(),
        db=None,
        tenant_id="demo",
        run_id=1,
        drive_folder_id="folder",
        take_count=5,
        selection_mode="auto",
        editing_goal="mostrar precios",
    )
    assert out.video_url == ""
    assert len(out.takes) == 1
    assert out.takes[0].drive_file_id == "file1"
    assert out.footage


def test_render_materializes_shorts_then_shotstack(monkeypatch: pytest.MonkeyPatch) -> None:
    import agents.marketing_agents.clip_reel_designer as designer_module

    monkeypatch.setattr(
        designer_module,
        "materialize_accepted_shorts",
        lambda db, tenant_id, run_id, takes: {"take-1": "http://localhost/static/shorts/take-1.mp4"},
    )
    monkeypatch.setattr(
        designer_module,
        "render_video",
        lambda timeline, render_provider=None: ("http://localhost/static/v.mp4", 1080, 1920),
    )

    takes = [
        TakeProposal(
            id="take-1",
            clip_id="clip1",
            drive_file_id="file1",
            trim_in=10.0,
            trim_out=20.0,
            duration_s=10.0,
            transcript="hola",
            is_hook=True,
            status="accepted",
            order=0,
        )
    ]
    out = ClipReelDesigner().render_from_takes(
        takes,
        strategy_hook="hook",
        db=object(),
        tenant_id="demo",
        run_id=9,
    )
    assert out.video_url.endswith(".mp4")
    assert out.takes[0].source_clip_url.endswith("take-1.mp4")
    assert out.takes[0].trim_in == 0.0


def test_video_producer_manual_ranges() -> None:
    tr = _long_transcript("clip1")
    agent = VideoProducerAgent()
    takes = agent.run(
        [tr],
        _brief(),
        _strategy(),
        footage_by_clip={"clip1": "fileABC"},
        take_count=5,
        selection_mode="manual",
        editing_goal="precios",
        manual_ranges=[
            {"file_id": "fileABC", "start_s": 0.0, "end_s": 8.0},
            {"file_id": "fileABC", "start_s": 20.0, "end_s": 28.0},
        ],
    )
    assert len(takes) == 2
    assert takes[0].drive_file_id == "fileABC"
    assert takes[0].is_hook is True


def test_video_producer_auto_stub_respects_take_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    agent = VideoProducerAgent()
    takes = agent.run(
        [_long_transcript("clip1")],
        _brief(),
        _strategy(),
        footage_by_clip={"clip1": "file1"},
        take_count=5,
        selection_mode="auto",
        editing_goal="precios y ubicacion",
    )
    assert 1 <= len(takes) <= 5
    assert sum(t.duration_s for t in takes) <= 90.0
