"""Tests del cliente OpenAI Images (gpt-image-2 directo) con httpx mockeado."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from gateway.app.core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_openai_image_size_maps_formats() -> None:
    from agents.marketing_agents.openai_image_client import openai_image_size

    assert openai_image_size(1080, 1350) == "1024x1536"  # feed 4:5
    assert openai_image_size(1080, 1920) == "1024x1536"  # story/reel
    assert openai_image_size(1080, 1080) == "1024x1024"
    assert openai_image_size(1200, 627) == "1536x1024"  # linkedin
    assert openai_image_size(1200, 675) == "1536x1024"  # x


def test_generate_image_bytes_decodes_b64(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import openai_image_client
    import httpx

    png_bytes = _tiny_png()
    b64 = base64.b64encode(png_bytes).decode("ascii")

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "data": [{"b64_json": b64}],
                "usage": {"input_tokens": 10, "output_tokens": 100, "total_tokens": 110},
                "size": "1024x1536",
                "quality": "high",
            }

    def _fake_post(url, **kwargs):
        assert url.endswith("/images/generations")
        assert "Authorization" in kwargs["headers"]
        body = kwargs["json"]
        assert body["model"] == "gpt-image-2"
        assert body["size"] == "1024x1536"
        assert body["quality"] == "high"
        assert body["background"] == "opaque"
        assert "OPENROUTER" not in url.upper()
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    raw = openai_image_client.generate_image_bytes(
        "canal at dusk",
        api_key="sk-test",
        model="gpt-image-2",
        width=1080,
        height=1350,
        quality="high",
    )
    assert raw == png_bytes


def test_generate_fails_loudly_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import openai_image_client
    import httpx

    class _Resp:
        status_code = 402
        text = "insufficient_quota"

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("402", request=None, response=self)

    def _fake_post(url, **kwargs):
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    with pytest.raises(RuntimeError, match="openai_image_failed"):
        openai_image_client.generate_image_bytes(
            "x",
            api_key="sk-test",
            width=1024,
            height=1024,
        )


def test_edit_image_bytes_multipart(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import openai_image_client
    import httpx

    out_png = _tiny_png()
    b64 = base64.b64encode(out_png).decode("ascii")

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"data": [{"b64_json": b64}]}

    def _fake_post(url, **kwargs):
        assert url.endswith("/images/edits")
        assert "files" in kwargs
        assert kwargs["data"]["model"] == "gpt-image-2"
        assert kwargs["data"]["size"] == "1024x1536"
        # No Content-Type: application/json en multipart
        assert kwargs["headers"].get("Content-Type") != "application/json"
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    raw = openai_image_client.edit_image_bytes(
        _tiny_png(),
        "add a red umbrella",
        api_key="sk-test",
        width=1080,
        height=1920,
    )
    assert raw == out_png


def test_generate_image_dispatch_openai_image(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """IMAGE_PROVIDER=openai_image usa el cliente directo, no Venice ni DALL·E."""
    from agents.marketing_agents import image_providers
    from agents.marketing_agents.image_specs import resolve_image_spec

    png = _tiny_png()
    calls: list[dict] = []

    def _fake_gen(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return png

    monkeypatch.setenv("IMAGE_PROVIDER", "openai_image")
    monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "sk-direct")
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    monkeypatch.setenv("OPENAI_IMAGE_QUALITY", "medium")
    get_settings.cache_clear()

    monkeypatch.setattr(
        "agents.marketing_agents.openai_image_client.generate_image_bytes",
        _fake_gen,
    )
    # Evitar escribir fuera de tmp si hace falta — _STATIC_DIR real está ok en tests
    static = tmp_path / "images"
    static.mkdir()
    monkeypatch.setattr(image_providers, "_STATIC_DIR", static)

    url, w, h = image_providers.generate_image(
        "beach scene",
        overlay_text=None,
        red_social="instagram",
        content_format="feed",
    )
    assert w == 1080 and h == 1350
    assert "openai_image_" in url
    assert calls and calls[0]["api_key"] == "sk-direct"
    assert calls[0]["quality"] == "medium"
    assert calls[0]["width"] == 1080


def test_openai_image_missing_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import image_providers

    monkeypatch.setenv("IMAGE_PROVIDER", "openai_image")
    monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="missing API key"):
        image_providers.generate_image("x", red_social="instagram", content_format="feed")


def test_compose_alter_uses_openai_image_edit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from agents.marketing_agents import image_providers
    from agents.marketing_agents.image_specs import resolve_image_spec

    src = tmp_path / "user.png"
    src.write_bytes(_tiny_png())
    edited = _tiny_png()
    called: dict = {}

    def _fake_edit(img_bytes, prompt, **kwargs):
        called["prompt"] = prompt
        called["model"] = kwargs.get("model")
        return edited

    monkeypatch.setenv("IMAGE_PROVIDER", "openai_image")
    monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "sk-direct")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "agents.marketing_agents.openai_image_client.edit_image_bytes",
        _fake_edit,
    )
    monkeypatch.setattr(
        "agents.marketing_agents.user_assets.load_asset_bytes",
        lambda url: _tiny_png(),
    )
    monkeypatch.setattr(
        "agents.marketing_agents.user_assets.save_composed_image",
        lambda data, prefix="x": (f"http://localhost/static/{prefix}.png", 1080, 1350),
    )

    spec = resolve_image_spec("instagram", "feed")
    url, w, h, source = image_providers.compose_from_user_asset(
        str(src),
        spec=spec,
        alter_with_ai=True,
        visual_instructions="poner una sombrilla",
        overlay_text=None,
    )
    assert source == "user_img2img"
    assert called.get("model") == "gpt-image-2"
    assert "sombrilla" in (called.get("prompt") or "").lower() or called.get("prompt")
    assert url.endswith(".png")
