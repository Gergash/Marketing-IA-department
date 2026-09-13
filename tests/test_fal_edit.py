"""Tests fal edit de foto real (paridad con Venice /image/edit)."""

from __future__ import annotations

import pytest


def test_fal_edit_mode_classifies_models() -> None:
    from agents.marketing_agents.image_providers import _fal_edit_mode

    assert _fal_edit_mode("fal-ai/flux-pro/kontext") == "instruction"
    assert _fal_edit_mode("fal-ai/qwen-image-2/edit") == "instruction"
    assert _fal_edit_mode("fal-ai/flux/dev/image-to-image") == "strength"
    assert _fal_edit_mode("") == "instruction"


def test_fal_edit_arguments_instruction_vs_strength() -> None:
    from agents.marketing_agents.image_providers import _fal_edit_arguments
    from agents.marketing_agents.image_specs import resolve_image_spec

    spec = resolve_image_spec("instagram", "feed")
    instr = _fal_edit_arguments(
        model="fal-ai/flux-pro/kontext",
        prompt="agrega dos personas en las sillas",
        image_url="https://fal.media/x.png",
        strength=0.72,
        guidance=3.5,
        spec=spec,
    )
    assert instr["prompt"].startswith("agrega")
    assert instr["image_url"].startswith("https://")
    assert instr["guidance_scale"] == 3.5
    assert "strength" not in instr
    assert "image_size" not in instr

    strength = _fal_edit_arguments(
        model="fal-ai/flux/dev/image-to-image",
        prompt="restyle",
        image_url="https://fal.media/x.png",
        strength=0.65,
        guidance=3.5,
        spec=spec,
    )
    assert strength["strength"] == 0.65
    assert "image_size" in strength
    assert strength["enable_safety_checker"] is False


def test_compose_from_user_asset_uses_fal_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con image_provider=fal + alter_with_ai, debe llamar fal edit (no Venice)."""
    from agents.marketing_agents import image_providers
    from agents.marketing_agents.image_specs import resolve_image_spec
    import agents.marketing_agents.user_assets as ua

    calls: dict = {}

    class _S:
        image_provider = "fal"
        fal_api_key = "fk"
        fal_img2img_model = "fal-ai/flux-pro/kontext"
        fal_img2img_strength = 0.72
        fal_img2img_guidance = 3.5
        venice_api_key = ""

    monkeypatch.setattr("gateway.app.core.settings.get_settings", lambda: _S())
    monkeypatch.setattr(ua, "load_asset_bytes", lambda url: b"SRC")
    monkeypatch.setattr(ua, "fit_image_to_spec", lambda raw, spec: raw)
    monkeypatch.setattr(
        ua,
        "save_composed_image",
        lambda raw, prefix="x": ("http://localhost:8000/static/images/x.png", 1080, 1350),
    )

    def _fake_fal(img, prompt, api_key, model, *, strength, guidance=3.5, spec):
        calls["prompt"] = prompt
        calls["model"] = model
        calls["api_key"] = api_key
        calls["guidance"] = guidance
        assert img == b"SRC"
        return b"EDITED"

    def _boom(*_a, **_k):
        raise AssertionError("Venice edit no debe llamarse con provider=fal")

    monkeypatch.setattr(image_providers, "_fal_img2img", _fake_fal)
    monkeypatch.setattr(image_providers, "_venice_edit", _boom)
    monkeypatch.setattr(image_providers, "_apply_layout_overlay", lambda *a, **k: b"FINAL")

    spec = resolve_image_spec("instagram", "feed")
    url, w, h, source = image_providers.compose_from_user_asset(
        "/static/uploads/site.jpg",
        spec=spec,
        overlay_text="Cena romántica",
        alter_with_ai=True,
        visual_instructions="agrega 2 personas sentadas en las sillas",
        image_provider="fal",
    )
    assert source == "user_img2img"
    assert calls["model"] == "fal-ai/flux-pro/kontext"
    assert "personas sentadas" in calls["prompt"].lower()
    assert "do not add" in calls["prompt"].lower() or "typography" in calls["prompt"].lower()
    assert url.endswith(".png")
