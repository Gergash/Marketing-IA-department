"""Tests del cliente Venice.ai (imagen síncrona + video queue/retrieve) con httpx mockeado."""

from __future__ import annotations

import base64

import pytest

from gateway.app.core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_venice_aspect_ratio_maps_reel() -> None:
    from agents.marketing_agents.venice_client import venice_aspect_ratio

    assert venice_aspect_ratio(1080, 1920) == "9:16"
    assert venice_aspect_ratio(1920, 1080) == "16:9"
    assert venice_aspect_ratio(1024, 1024) == "1:1"


def test_normalize_base_fixes_legacy_v1_path() -> None:
    from agents.marketing_agents.venice_client import _normalize_base

    assert _normalize_base("https://api.venice.ai/v1") == "https://api.venice.ai/api/v1"
    assert _normalize_base("https://api.venice.ai/api/v1/") == "https://api.venice.ai/api/v1"


def test_generate_image_bytes_decodes_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import venice_client
    import httpx

    png_bytes = b"\x89PNG\r\n\x1a\nfake"
    b64 = base64.b64encode(png_bytes).decode("ascii")

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"id": "gen-1", "images": [b64]}

    def _fake_post(url, **kwargs):
        assert url.endswith("/image/generate")
        assert "Authorization" in kwargs["headers"]
        body = kwargs["json"]
        assert body["model"] == "venice-sd35"
        assert body["width"] == 1024
        assert body["height"] == 1024
        assert len(body["prompt"]) <= 1500
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)

    raw = venice_client.generate_image_bytes(
        "canal at dusk",
        api_key="test-key",
        model="venice-sd35",
        width=1024,
        height=1024,
    )
    assert raw == png_bytes


def test_clamp_pixel_dimensions_instagram_feed() -> None:
    from agents.marketing_agents.venice_client import clamp_pixel_dimensions

    w, h = clamp_pixel_dimensions(1080, 1350)
    assert w <= 1280 and h <= 1280
    assert w >= 512 and h >= 512
    # Mantiene orientación portrait
    assert h > w


def test_generate_image_bytes_clamps_height_for_sd35(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import venice_client
    import httpx

    png_bytes = b"img"
    b64 = base64.b64encode(png_bytes).decode("ascii")

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"images": [b64]}

    def _fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["height"] <= 1280
        assert body["width"] <= 1280
        assert len(body["prompt"]) <= 1500
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    raw = venice_client.generate_image_bytes(
        "x" * 5000,  # prompt largo → truncado
        api_key="k",
        model="venice-sd35",
        width=1080,
        height=1350,
    )
    assert raw == png_bytes


def test_generate_image_bytes_aspect_ratio_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import venice_client
    import httpx

    png_bytes = b"img"
    b64 = base64.b64encode(png_bytes).decode("ascii")

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"images": [b64]}

    def _fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["model"] == "qwen-image-2"
        assert body["aspect_ratio"] == "9:16"
        assert "width" not in body
        assert "resolution" not in body
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    raw = venice_client.generate_image_bytes(
        "vertical ad",
        api_key="k",
        model="qwen-image-2",
        width=1080,
        height=1920,
    )
    assert raw == png_bytes


def test_generate_image_bytes_nano_banana_pro(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import venice_client
    import httpx

    png_bytes = b"banana"
    b64 = base64.b64encode(png_bytes).decode("ascii")

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"images": [b64]}

    def _fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["model"] == "nano-banana-pro"
        assert body["aspect_ratio"] == "4:5"
        assert body["resolution"] == "2K"
        assert "width" not in body
        assert "height" not in body
        assert "negative_prompt" not in body
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    raw = venice_client.generate_image_bytes(
        "gourmet steak campaign photo",
        api_key="k",
        model="nano-banana-pro",
        width=1080,
        height=1350,
        resolution="2K",
    )
    assert raw == png_bytes


def test_generate_image_bytes_gpt_image_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """gpt-image-2 vía Venice: aspect_ratio + resolution (sin width/height)."""
    from agents.marketing_agents import venice_client
    import httpx

    png_bytes = b"gpt-image-2"
    b64 = base64.b64encode(png_bytes).decode("ascii")

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"images": [b64]}

    def _fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["model"] == "gpt-image-2"
        assert body["aspect_ratio"] == "4:5"
        assert body["resolution"] == "2K"
        assert "width" not in body
        assert "height" not in body
        assert "negative_prompt" not in body
        assert "style_preset" not in body
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    raw = venice_client.generate_image_bytes(
        "romantic dinner terrace fairy lights couples date night",
        api_key="k",
        model="gpt-image-2",
        width=1080,
        height=1350,
        resolution="2K",
        style_preset="cinematic",  # debe ignorarse en resolution-tier
    )
    assert raw == png_bytes


def test_prompt_limit_gpt_image_2() -> None:
    from agents.marketing_agents.venice_client import prompt_limit_for_model

    assert prompt_limit_for_model("gpt-image-2") == 4000


def test_prompt_limit_nano_vs_sd35() -> None:
    from agents.marketing_agents.venice_client import prompt_limit_for_model, truncate_prompt

    assert prompt_limit_for_model("venice-sd35") == 1500
    assert prompt_limit_for_model("nano-banana-pro") == 7500
    truncated = truncate_prompt("a" * 5000, "venice-sd35")
    assert len(truncated) <= 1500


def test_generate_video_bytes_polls_until_mp4(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from agents.marketing_agents import venice_client
    import httpx

    monkeypatch.setattr(venice_client.time, "sleep", lambda *_: None)
    monkeypatch.setattr(venice_client, "_STATIC_VIDEOS", tmp_path)

    calls = {"n": 0}

    class _QueueResp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"model": "wan-2.5-preview-image-to-video", "queue_id": "q-1"}

    class _PollJson:
        headers = {"Content-Type": "application/json"}

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"status": "PROCESSING"}

    class _PollMp4:
        headers = {"Content-Type": "video/mp4"}
        content = b"FAKEMP4"

        def raise_for_status(self) -> None:
            return None

    class _CompleteResp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"success": True}

    def _fake_post(url, **kwargs):
        if url.endswith("/video/queue"):
            return _QueueResp()
        if url.endswith("/video/retrieve"):
            calls["n"] += 1
            if calls["n"] == 1:
                return _PollJson()
            return _PollMp4()
        if url.endswith("/video/complete"):
            return _CompleteResp()
        raise AssertionError(url)

    monkeypatch.setattr(httpx, "post", _fake_post)

    raw = venice_client.generate_video_bytes(
        "slow zoom",
        api_key="k",
        model="wan-2.5-preview-image-to-video",
        image_url="data:image/png;base64,aaa",
        max_wait_seconds=60,
    )
    assert raw == b"FAKEMP4"
    assert calls["n"] >= 2


def test_image_provider_venice_saves_static(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("IMAGE_PROVIDER", "venice")
    monkeypatch.setenv("VENICE_API_KEY", "test-key")
    get_settings.cache_clear()

    from agents.marketing_agents import image_providers
    import httpx

    monkeypatch.setattr(image_providers, "_STATIC_DIR", tmp_path)

    png_bytes = b"\x89PNG\r\n\x1a\nfakeimg"
    b64 = base64.b64encode(png_bytes).decode("ascii")

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"images": [b64]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())

    url, w, h = image_providers.generate_image(
        "producto demo",
        image_provider="venice",
        red_social="instagram",
        content_format="feed",
    )
    assert url.startswith("http://localhost:8000/static/images/venice_")
    assert (tmp_path / url.rsplit("/", 1)[-1]).read_bytes() == png_bytes
    assert w == 1080
    assert h == 1350


def test_video_designer_animates_scenes_when_venice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEO_SCENE_PROVIDER", "venice")
    monkeypatch.setenv("VENICE_API_KEY", "test-key")
    monkeypatch.setenv("VIDEO_PROVIDER", "mock")
    monkeypatch.setenv("VOICE_PROVIDER", "mock")
    get_settings.cache_clear()

    from agents.marketing_agents import video_designer as vd
    from agents.marketing_agents.schemas import BriefInput, CopyOutput, StrategyOutput
    from agents.marketing_agents.video_script import ScriptScene, VideoScript

    class _FakeScript:
        def run(self, *a, **k):
            scene = ScriptScene(
                visual_prompt="oficina moderna",
                headline="Ahorra",
                subline="tiempo",
                narration="Ahorra tiempo cada día.",
            )
            return VideoScript(hook="Hook", cta="Escribe DEMO", scenes=[scene, scene, scene])

    monkeypatch.setattr(
        vd, "generate_image", lambda *a, **k: ("http://localhost:8000/static/images/x.png", 1080, 1920)
    )
    monkeypatch.setattr(
        vd, "synthesize_voice", lambda *a, **k: ("http://localhost:8000/static/audio/v.wav", 15.0)
    )
    monkeypatch.setattr(
        vd,
        "_animate_scene_with_venice",
        lambda *a, **k: ("http://localhost:8000/static/videos/scene.mp4", 5.0),
    )

    captured = {}

    def _capture_render(timeline, **kwargs):
        captured["timeline"] = timeline
        return ("http://localhost:8000/static/videos/out.mp4", 1080, 1920)

    monkeypatch.setattr(vd, "render_video", _capture_render)

    agent = vd.VideoDesignerAgent(script_agent=_FakeScript())
    out = agent.run(
        BriefInput(
            tema="producto X",
            publico_objetivo="audiencia Y",
            red_social="instagram",
            objetivo="branding",
        ),
        CopyOutput(copy_final="copy", hashtags=["#a"], cta="CTA"),
        StrategyOutput(
            tipo_post="educativo",
            hook="hook",
            mensaje_base="mensaje",
            hashtags=["#a"],
        ),
    )
    assert out.video_url.endswith(".mp4")
    assert captured["timeline"].scenes[0].asset_type == "video"
    assert captured["timeline"].scenes[0].background_url.endswith("scene.mp4")
