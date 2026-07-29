"""Pruebas del branch de video en MarketingPipeline: content_format="reel" vs regresion feed."""

import pytest

from agents.marketing_agents import BriefInput, MarketingPipeline


@pytest.fixture(autouse=True)
def _mock_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("SOCIAL_PROVIDER", "mock")
    # Fuerza fallback a stubs deterministas (sin red) en estratega/copy/guion.
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")


@pytest.fixture(autouse=True)
def _mock_video_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    import agents.marketing_agents.video_designer as video_designer_module

    def _fake_generate_image(prompt, **kwargs):
        return "http://localhost:8000/static/images/scene.png", 1080, 1920

    def _fake_synthesize_voice(text, **kwargs):
        words = len(text.split())
        return "http://localhost:8000/static/audio/vo.wav", max(1.0, words / 2.5)

    def _fake_render_video(timeline, **kwargs):
        return "http://localhost:8000/static/videos/reel.mp4", timeline.output.width, timeline.output.height

    monkeypatch.setattr(video_designer_module, "generate_image", _fake_generate_image)
    monkeypatch.setattr(video_designer_module, "synthesize_voice", _fake_synthesize_voice)
    monkeypatch.setattr(video_designer_module, "render_video", _fake_render_video)


def _brief() -> BriefInput:
    return BriefInput(
        tema="automatizacion de marketing",
        publico_objetivo="dueños de negocio",
        red_social="instagram",
        objetivo="branding",
    )


def test_reel_run_returns_video_design_output() -> None:
    """content_format="reel" debe usar el branch de video: video_url poblado, image_url ausente/None."""
    pipeline = MarketingPipeline()
    result = pipeline.run(_brief(), publish=False, content_format="reel")

    design = result["design"]
    assert design["video_url"] == "http://localhost:8000/static/videos/reel.mp4"
    assert design.get("image_url") is None
    assert 3 <= design["scene_count"] <= 5


def test_feed_run_unchanged_image_shape_regression() -> None:
    """content_format="feed" (default) debe seguir devolviendo el shape de imagen sin tocar el branch de video."""
    pipeline = MarketingPipeline()
    result = pipeline.run(_brief(), publish=False, content_format="feed")

    design = result["design"]
    assert design.get("image_url")
    assert design.get("image_width") == 1080
    assert design.get("image_height") == 1350
    assert "video_url" not in design


def test_user_clip_reel_skips_image_publisher_and_routes_to_go(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate WARNING #1: content_format="user_clip_reel" NO debe pasar por PublisherAgent (guard widen)."""
    from agents.marketing_agents.schemas import VideoDesignOutput

    pipeline = MarketingPipeline()

    def _fake_clip_reel_run(brief, copy, strategy, **kwargs):
        return VideoDesignOutput(
            image_url=None,
            video_url="http://localhost:8000/static/videos/clipreel.mp4",
            video_prompt=strategy.hook,
            video_provider="shotstack",
            voice_provider="",
            width=1080,
            height=1920,
            duration_s=20.0,
            scene_count=2,
            layout_archetype="typographic_poster",
        )

    monkeypatch.setattr(pipeline.clip_reel_designer, "run", _fake_clip_reel_run)

    publisher_calls = {"count": 0}
    monkeypatch.setattr(pipeline.publisher, "run", lambda *a, **kw: publisher_calls.__setitem__("count", publisher_calls["count"] + 1))

    result = pipeline.run(
        _brief(),
        publish=True,
        content_format="user_clip_reel",
        db=None,
        tenant_id="demo-tenant",
        run_id=1,
        drive_folder_id="folder123",
    )

    assert result["design"]["video_url"] == "http://localhost:8000/static/videos/clipreel.mp4"
    assert result["publish_result"] is None
    assert publisher_calls["count"] == 0  # guard widen: nunca pasa por el PublisherAgent de imagen


def test_reel_still_skips_image_publisher_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regresion del guard widen: content_format="reel" sigue sin pasar por PublisherAgent."""
    pipeline = MarketingPipeline()

    publisher_calls = {"count": 0}
    monkeypatch.setattr(pipeline.publisher, "run", lambda *a, **kw: publisher_calls.__setitem__("count", publisher_calls["count"] + 1))

    result = pipeline.run(_brief(), publish=True, content_format="reel")

    assert result["publish_result"] is None
    assert publisher_calls["count"] == 0
