"""Pruebas Design-as-Code: foto de usuario + overlay Pillow."""

import io

import pytest
from PIL import Image

from agents.marketing_agents.image_providers import compose_from_user_asset
from agents.marketing_agents.image_specs import resolve_image_spec
from agents.marketing_agents.layout_archetypes import _ARCHETYPE_MAP
from agents.marketing_agents.user_assets import fit_image_to_spec, local_url_for_upload


def _make_test_png(w: int = 800, h: int = 600) -> bytes:
    img = Image.new("RGB", (w, h), color=(40, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def user_asset_url(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Guarda PNG de prueba en static/uploads y devuelve URL local."""
    from agents.marketing_agents import user_assets

    static = tmp_path / "static"
    uploads = static / "uploads"
    images = static / "images"
    uploads.mkdir(parents=True)
    images.mkdir(parents=True)
    monkeypatch.setattr(user_assets, "_STATIC_ROOT", static)
    monkeypatch.setattr(user_assets, "_UPLOADS_DIR", uploads)
    monkeypatch.setattr(user_assets, "_IMAGES_DIR", images)

    from agents.marketing_agents import image_providers

    monkeypatch.setattr(image_providers, "_STATIC_DIR", images)

    name = "test_photo.png"
    (uploads / name).write_bytes(_make_test_png())
    return local_url_for_upload(name)


def test_fit_image_to_spec_preserves_content(user_asset_url: str) -> None:
    from agents.marketing_agents.user_assets import load_asset_bytes

    spec = resolve_image_spec("instagram", "feed")
    raw = load_asset_bytes(user_asset_url)
    fitted = fit_image_to_spec(raw, spec)
    img = Image.open(io.BytesIO(fitted))
    assert img.size == (spec.width, spec.height)


def test_compose_user_overlay_no_fal(user_asset_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    spec = resolve_image_spec("linkedin", "feed")
    archetype = _ARCHETYPE_MAP["minimal_conceptual"]
    url, w, h, source = compose_from_user_asset(
        user_asset_url,
        spec=spec,
        overlay_text="Titulo de prueba",
        overlay_subline="Sublinea",
        overlay_cta="Ver mas",
        layout_archetype=archetype.id,
        alter_with_ai=False,
    )
    assert source == "user_overlay"
    assert w == spec.width
    assert h == spec.height
    assert "/static/images/user_overlay_" in url
