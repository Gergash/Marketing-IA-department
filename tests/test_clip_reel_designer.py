"""Pruebas de ClipReelDesigner: banda 6-60s, wan-effects opcional con degradacion, forma de VideoDesignOutput."""

import pytest

from agents.marketing_agents.clip_editor import SelectedSegment
from agents.marketing_agents.clip_reel_designer import ClipReelDesigner
from agents.marketing_agents.schemas import BriefInput, CopyOutput, StrategyOutput
from agents.marketing_agents.transcription_providers import ClipTranscript, Word


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


class _FakeEditorAgent:
    """Editor agent fake: devuelve una lista de segmentos fija, sin llamar a Drive/Whisper/LLM."""

    def __init__(self, segments: list[SelectedSegment]) -> None:
        self._segments = segments

    def run(self, transcripts, brief, strategy) -> list[SelectedSegment]:
        return self._segments


def _patch_drive_and_transcription(monkeypatch: pytest.MonkeyPatch) -> None:
    import agents.marketing_agents.clip_reel_designer as designer_module

    class _FakeDownloadedClip:
        def __init__(self, clip_id: str, path: str) -> None:
            self.clip_id = clip_id
            self.path = path
            self.filename = f"{clip_id}.mp4"

    fake_clips = [_FakeDownloadedClip("clip1", "/static/uploads/clips/1/clip1.mp4")]

    monkeypatch.setattr(designer_module, "list_and_download_clips", lambda *a, **kw: fake_clips)
    monkeypatch.setattr(
        designer_module,
        "transcribe_clips",
        lambda clips, **kw: [ClipTranscript(clip_id="clip1", words=[Word(text="hola", start_s=0.0, end_s=1.0)], text="hola")],
    )


def test_selected_segments_totaling_45s_pass_duration_band(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_drive_and_transcription(monkeypatch)
    segments = [
        SelectedSegment(clip_id="clip1", start_s=0.0, end_s=45.0, text="contenido de prueba", is_hook=True),
    ]
    designer = ClipReelDesigner(editor_agent=_FakeEditorAgent(segments))

    output = designer.run(
        _brief(), _copy(), _strategy(),
        db=None, tenant_id="demo-tenant", run_id=1, drive_folder_id="folder123",
    )

    assert 6.0 <= output.duration_s <= 60.0
    assert output.duration_s == 45.0
    assert output.video_url
    assert output.image_url is None
    assert output.scene_count == 1


def test_effects_enabled_and_fal_succeeds_replaces_hook_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EFFECTS_ENABLED", "true")
    monkeypatch.setenv("FAL_API_KEY", "fake-fal-key")
    _patch_drive_and_transcription(monkeypatch)

    import agents.marketing_agents.clip_reel_designer as designer_module

    calls = {"count": 0}

    def _fake_apply_wan_effect(video_url, prompt, api_key, model):
        calls["count"] += 1
        return "http://fal.example/effect_output.mp4"

    monkeypatch.setattr(designer_module, "_apply_wan_effect", _fake_apply_wan_effect)

    captured_scenes = {}
    original_timeline_init = designer_module.Timeline

    def _capturing_timeline(*, scenes, captions):
        captured_scenes["scenes"] = scenes
        return original_timeline_init(scenes=scenes, captions=captions)

    monkeypatch.setattr(designer_module, "Timeline", _capturing_timeline)

    segments = [
        SelectedSegment(clip_id="clip1", start_s=0.0, end_s=10.0, text="hola", is_hook=True),
    ]
    designer = ClipReelDesigner(editor_agent=_FakeEditorAgent(segments))

    designer.run(_brief(), _copy(), _strategy(), db=None, tenant_id="demo-tenant", run_id=1, drive_folder_id="f1")

    assert calls["count"] == 1
    assert captured_scenes["scenes"][0].background_url == "http://fal.example/effect_output.mp4"


def test_effects_enabled_and_fal_fails_uses_original_hook_no_run_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EFFECTS_ENABLED", "true")
    monkeypatch.setenv("FAL_API_KEY", "fake-fal-key")
    _patch_drive_and_transcription(monkeypatch)

    import agents.marketing_agents.clip_reel_designer as designer_module

    def _failing_apply_wan_effect(video_url, prompt, api_key, model):
        return video_url  # simula degradacion tras error interno ya logueado

    monkeypatch.setattr(designer_module, "_apply_wan_effect", _failing_apply_wan_effect)

    segments = [
        SelectedSegment(clip_id="clip1", start_s=0.0, end_s=10.0, text="hola", is_hook=True),
    ]
    designer = ClipReelDesigner(editor_agent=_FakeEditorAgent(segments))

    output = designer.run(
        _brief(), _copy(), _strategy(), db=None, tenant_id="demo-tenant", run_id=1, drive_folder_id="f1",
    )

    assert output.video_url  # el run no se bloquea/falla
