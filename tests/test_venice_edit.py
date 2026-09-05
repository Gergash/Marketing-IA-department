"""Tests Venice /image/edit (foto real → agregar personas/objetos)."""

from __future__ import annotations

import base64

import pytest


def test_edit_model_for_generate_model() -> None:
    from agents.marketing_agents.venice_client import edit_model_for_generate_model

    assert edit_model_for_generate_model("gpt-image-2") == "gpt-image-2-edit"
    assert edit_model_for_generate_model("nano-banana-pro") == "nano-banana-pro-edit"
    assert edit_model_for_generate_model("gpt-image-2-edit") == "gpt-image-2-edit"


def test_edit_image_bytes_returns_png(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import venice_client
    import httpx

    png_out = b"\x89PNG\r\n\x1a\nedited"

    class _Resp:
        content = png_out
        headers = {"Content-Type": "image/png"}

        def raise_for_status(self) -> None:
            return None

    def _fake_post(url, **kwargs):
        assert url.endswith("/image/edit")
        body = kwargs["json"]
        assert body["model"] == "gpt-image-2-edit"
        assert "agrega una pareja" in body["prompt"].lower()
        assert body["image"]  # base64
        assert body.get("resolution") == "2K"
        # quality NO debe enviarse (schema Venice → 400)
        assert "quality" not in body
        # Debe ser JPEG re-encoded
        raw = base64.b64decode(body["image"])
        assert raw[:2] == b"\xff\xd8"
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    # JPEG mínimo válido vía Pillow
    import io
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (512, 512), color=(20, 30, 40)).save(buf, format="JPEG")
    out = venice_client.edit_image_bytes(
        buf.getvalue(),
        "agrega una pareja sentada en las sillas",
        api_key="k",
        model="gpt-image-2-edit",
        resolution="2K",
        quality="high",  # se ignora / no se envía
    )
    assert out == png_out


def test_compose_from_user_asset_uses_venice_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con IMAGE_PROVIDER=venice + alter_with_ai, debe llamar edit y no fal."""
    from agents.marketing_agents import image_providers
    from agents.marketing_agents.image_specs import resolve_image_spec
    import agents.marketing_agents.user_assets as ua

    calls: dict = {}

    class _S:
        image_provider = "venice"
        venice_api_key = "vk"
        venice_api_base = "https://api.venice.ai/api/v1"
        venice_image_model = "gpt-image-2"
        venice_image_edit_model = "gpt-image-2-edit"
        venice_image_resolution = "2K"
        venice_image_edit_quality = "high"
        fal_api_key = ""

    monkeypatch.setattr("gateway.app.core.settings.get_settings", lambda: _S())
    monkeypatch.setattr(ua, "load_asset_bytes", lambda url: b"SRC")
    monkeypatch.setattr(ua, "fit_image_to_spec", lambda raw, spec: raw)
    monkeypatch.setattr(
        ua,
        "save_composed_image",
        lambda raw, prefix="x": ("http://localhost:8000/static/images/x.png", 1080, 1350),
    )

    def _fake_venice_edit(img, prompt, **kwargs):
        calls["prompt"] = prompt
        calls["model"] = kwargs.get("edit_model")
        return b"EDITED"

    monkeypatch.setattr(image_providers, "_venice_edit", _fake_venice_edit)
    monkeypatch.setattr(image_providers, "_apply_layout_overlay", lambda *a, **k: b"FINAL")

    spec = resolve_image_spec("instagram", "feed")
    url, w, h, source = image_providers.compose_from_user_asset(
        "/static/uploads/site.jpg",
        spec=spec,
        overlay_text="Cena romántica",
        alter_with_ai=True,
        visual_instructions="agrega 2 personas sentadas en las sillas",
        image_provider="venice",
    )
    assert source == "user_img2img"
    assert "personas sentadas" in calls["prompt"].lower()
    assert "do not add" in calls["prompt"].lower() or "typography" in calls["prompt"].lower()
    assert url.endswith(".png")
