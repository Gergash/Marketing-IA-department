"""Tests de composición PIL para los 4 layouts editoriales de design_layouts.py."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from agents.marketing_agents.design_layouts import apply_design_layout
from agents.marketing_agents.layout_archetypes import _ARCHETYPE_MAP, LayoutArchetype


def _make_png(width: int = 300, height: int = 375, color: tuple = (80, 120, 160)) -> bytes:
    """Crea un PNG RGB mínimo en memoria para usar como imagen de entrada."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _assert_valid_png(data: bytes, expected_w: int, expected_h: int) -> None:
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"
    assert img.mode == "RGB"
    assert img.size == (expected_w, expected_h)


# ---------------------------------------------------------------------------
# Parametrize over all 4 archetypes
# ---------------------------------------------------------------------------

ALL_ARCHETYPES = list(_ARCHETYPE_MAP.values())


@pytest.mark.parametrize("archetype", ALL_ARCHETYPES, ids=[a.id for a in ALL_ARCHETYPES])
def test_layout_produces_valid_png(archetype: LayoutArchetype) -> None:
    """Cada handler devuelve un PNG RGB con las mismas dimensiones que la imagen de entrada."""
    W, H = 300, 375
    result = apply_design_layout(
        _make_png(W, H),
        archetype,
        headline="Headline de prueba",
        subline="Subtítulo opcional",
        cta="Saber más",
    )
    _assert_valid_png(result, W, H)


@pytest.mark.parametrize("archetype", ALL_ARCHETYPES, ids=[a.id for a in ALL_ARCHETYPES])
def test_layout_without_optional_fields(archetype: LayoutArchetype) -> None:
    """Los layouts no crashean cuando subline y cta son None."""
    result = apply_design_layout(
        _make_png(300, 375),
        archetype,
        headline="Solo headline",
        subline=None,
        cta=None,
    )
    assert isinstance(result, bytes)
    assert len(result) > 0


@pytest.mark.parametrize("archetype", ALL_ARCHETYPES, ids=[a.id for a in ALL_ARCHETYPES])
def test_layout_with_long_headline(archetype: LayoutArchetype) -> None:
    """Los layouts no crashean con un headline largo (se wrappea, no se desborda)."""
    long_headline = "Transforma tu estrategia de marketing digital con inteligencia artificial avanzada"
    result = apply_design_layout(
        _make_png(300, 375),
        archetype,
        headline=long_headline,
        subline="Subtítulo adicional de prueba",
        cta="Ver más",
    )
    _assert_valid_png(result, 300, 375)


def test_dispatcher_routes_unknown_id_to_typographic() -> None:
    """apply_design_layout usa typographic_poster como fallback ante IDs desconocidos."""
    unknown = LayoutArchetype(
        id="unknown_archetype",
        label="Test",
        flux_style="test",
        flux_composition="test",
        primary_hex="#FFFFFF",
        secondary_hex="#000000",
        accent_hex="#FF0000",
    )
    result = apply_design_layout(
        _make_png(300, 375),
        unknown,
        headline="Fallback test",
        subline=None,
        cta=None,
    )
    _assert_valid_png(result, 300, 375)


def test_layout_preserves_aspect_ratio_story() -> None:
    """Los layouts mantienen dimensiones story (810×1440) sin recortar ni escalar."""
    W, H = 810, 1440
    archetype = _ARCHETYPE_MAP["cinematic_hero"]
    result = apply_design_layout(
        _make_png(W, H),
        archetype,
        headline="Historia",
        subline="Story test",
        cta=None,
        content_format="story",
    )
    _assert_valid_png(result, W, H)


@pytest.mark.parametrize("archetype", ALL_ARCHETYPES, ids=[a.id for a in ALL_ARCHETYPES])
def test_story_layout_centers_overlay(archetype: LayoutArchetype) -> None:
    """En story, el overlay altera el centro de la imagen (no solo el tercio inferior izquierdo)."""
    W, H = 540, 960
    base_color = (90, 100, 110)
    result = apply_design_layout(
        _make_png(W, H, base_color),
        archetype,
        headline="Texto central",
        subline="Más centrado",
        cta="Ver más",
        content_format="story",
    )
    img = Image.open(io.BytesIO(result)).convert("RGB")
    center = img.getpixel((W // 2, H // 2))
    # El centro debe diferir del fondo plano por viñeta/texto
    assert center != base_color

    feed = apply_design_layout(
        _make_png(W, H, base_color),
        archetype,
        headline="Texto feed",
        subline="Abajo",
        cta="Ver más",
        content_format="feed",
    )
    assert result != feed

