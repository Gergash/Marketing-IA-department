"""Tests del pack tipográfico OFL, roles display/body/cta y guards anti-texto."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from agents.marketing_agents.brand_visual import resolve_brand_font_paths
from agents.marketing_agents.design_layouts import apply_design_layout
from agents.marketing_agents.layout_archetypes import (
    _ARCHETYPE_MAP,
    build_flux_prompt,
)
from agents.marketing_agents.overlay_text import (
    pack_font_roles,
    resolve_font_roles,
    split_brand_highlight,
)
from agents.marketing_agents.visual_prompt_guards import (
    NO_TEXT_NEGATIVE,
    NO_TEXT_PHOTO_SUFFIX,
    with_photo_only_guard,
)
from agents.marketing_agents.image_specs import resolve_image_spec
from agents.marketing_agents.schemas import BriefInput, StrategyOutput


def test_pack_font_roles_finds_project_ttfs() -> None:
    roles = pack_font_roles()
    assert roles is not None
    for path in (roles.display, roles.body, roles.cta, roles.tagline):
        assert Path(path).is_file()
        assert path.endswith(".ttf")
    assert "GreatVibes" in Path(roles.display).name
    assert "Montserrat" in Path(roles.body).name
    assert "Montserrat" in Path(roles.cta).name
    assert "Playfair" in Path(roles.tagline).name


def test_resolve_font_roles_prefers_script_display() -> None:
    roles = resolve_font_roles(font_seed="instagram", prefer_script_display=True)
    assert "GreatVibes" in Path(roles.display).name
    assert Path(roles.body).is_file()


def test_resolve_brand_font_paths_maps_script_to_pack() -> None:
    paths = resolve_brand_font_paths(
        ["Caligráfico", "Sans"],
        brand_text="Tipografía caligráfica y sans limpia",
    )
    assert paths
    assert any("GreatVibes" in p for p in paths)
    assert any("Montserrat" in p for p in paths)


def test_split_brand_highlight_marks_brand() -> None:
    segs = split_brand_highlight("Reserva en Tres Amores hoy", ["Tres Amores"])
    assert any(is_brand for _t, is_brand in segs)
    joined = "".join(t for t, _ in segs)
    assert "Tres Amores" in joined


def test_brand_campaign_piece_uses_pack_fonts_and_cta() -> None:
    W, H = 480, 600
    img = Image.new("RGB", (W, H), (35, 28, 22))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    archetype = _ARCHETYPE_MAP["brand_campaign_piece"]
    result = apply_design_layout(
        buf.getvalue(),
        archetype,
        headline="Celebra Amor y Amistad",
        subline="Reserva tu mesa en Tres Amores",
        cta="Cupos limitados · Escríbenos por DM",
        brand_names=["Tres Amores"],
        tagline="Donde cada encuentro se convierte en un recuerdo.",
    )
    out = Image.open(io.BytesIO(result))
    assert out.format == "PNG"
    assert out.size == (W, H)


def test_with_photo_only_guard_forbids_brand_manual_collage() -> None:
    guarded = with_photo_only_guard("Warm coffee shop interior")
    lower = guarded.lower()
    assert "full-bleed photograph" in lower
    assert "no brand manuals" in lower
    assert "no collages" in lower
    assert "brand manuals" in NO_TEXT_PHOTO_SUFFIX.lower()
    assert "collage" in NO_TEXT_NEGATIVE.lower()


def test_build_flux_prompt_contains_anti_collage_guard() -> None:
    brief = BriefInput(
        tema="Amor y Amistad en Tres Amores",
        publico_objetivo="parejas",
        red_social="instagram",
        objetivo="conversiones",
        brand_context="Marca: Tres Amores · Café · tipografía caligráfica · dorado y café",
    )
    strategy = StrategyOutput(
        tipo_post="promocional",
        hook="hook",
        mensaje_base="msg",
        hashtags=[],
    )
    archetype = _ARCHETYPE_MAP["brand_campaign_piece"]
    prompt = build_flux_prompt(
        archetype,
        brief=brief,
        strategy=strategy,
        spec=resolve_image_spec("instagram", "feed"),
    )
    lower = prompt.lower()
    assert "no brand manuals" in lower
    assert "full-bleed photograph" in lower
    assert "no collages" in lower or "no collage" in lower
