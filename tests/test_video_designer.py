"""Pruebas de VideoDesignerAgent: guion (stub) -> fondos/voz/render mockeados -> VideoDesignOutput."""

import pytest

from agents.marketing_agents.schemas import BriefInput, CopyOutput, StrategyOutput
from agents.marketing_agents.video_designer import VideoDesignerAgent


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fuerza fallback a stub en VideoScriptAgent (sin red, determinista)
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
        hashtags=["#IA", "#MarketingDigital"],
    )


def _copy() -> CopyOutput:
    return CopyOutput(
        copy_final="Automatiza tu marketing con IA y recupera tu tiempo.",
        hashtags=["#IA", "#MarketingDigital"],
        cta="Escribe DEMO y te mostramos como.",
        headline_for_image="Automatiza tu marketing con IA",
        subline_for_image="Recupera tu tiempo cada semana",
    )


def test_video_designer_run_returns_video_design_output(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"generate_image": 0, "synthesize_voice": 0, "render_video": 0}

    def _fake_generate_image(prompt, **kwargs):
        calls["generate_image"] += 1
        return f"http://localhost:8000/static/images/scene_{calls['generate_image']}.png", 1080, 1920

    def _fake_synthesize_voice(text, **kwargs):
        calls["synthesize_voice"] += 1
        words = len(text.split())
        return "http://localhost:8000/static/audio/vo.wav", max(1.0, words / 2.5)

    def _fake_render_video(timeline, **kwargs):
        calls["render_video"] += 1
        assert timeline.voiceover is not None
        assert any((s.narration or "").strip() for s in timeline.scenes)
        return "http://localhost:8000/static/videos/reel.mp4", timeline.output.width, timeline.output.height

    import agents.marketing_agents.video_designer as video_designer_module

    monkeypatch.setattr(video_designer_module, "generate_image", _fake_generate_image)
    monkeypatch.setattr(video_designer_module, "synthesize_voice", _fake_synthesize_voice)
    monkeypatch.setattr(video_designer_module, "render_video", _fake_render_video)

    agent = VideoDesignerAgent()
    output = agent.run(_brief(), _copy(), _strategy())

    assert output.video_url == "http://localhost:8000/static/videos/reel.mp4"
    assert output.image_url is None
    assert 3 <= output.scene_count <= 5
    assert 15.0 <= output.duration_s <= 30.0
    assert output.width == 1080
    assert output.height == 1920
    assert calls["generate_image"] == output.scene_count
    assert calls["synthesize_voice"] == 1
    assert calls["render_video"] == 1
