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
    # Body bajo título: siempre grueso (Bold/ExtraBold/Black)
    body = Path(roles.body).stem.lower()
    assert "montserrat" in body or "poppins" in body or "nunito" in body
    assert any(w in body for w in ("bold", "black", "heavy"))
    assert "regular" not in body
    cta = Path(roles.cta).stem.lower()
    assert any(w in cta for w in ("bold", "black", "heavy"))
    tag = Path(roles.tagline).stem.lower()
    assert "playfair" in tag or "slab" in tag or "bold" in tag


def test_resolve_font_roles_prefers_script_display() -> None:
    roles = resolve_font_roles(font_seed="instagram", prefer_script_display=True)
    assert "GreatVibes" in Path(roles.display).name
    assert Path(roles.body).is_file()
    assert "regular" not in Path(roles.body).stem.lower()


def test_font_catalog_varies_by_seed() -> None:
    from agents.marketing_agents.overlay_text import list_font_families, pick_font_family

    families = list_font_families()
    assert len(families) >= 6
    a = pick_font_family("typographic_poster:instagram:cafe", prefer_script=False)
    b = pick_font_family("cinematic_hero:linkedin:tech summit 2026", prefer_script=False)
    assert a is not None and b is not None
    # Con catálogo amplio, seeds distintos suelen elegir familias distintas
    ids = {pick_font_family(f"seed-{i}", prefer_script=False).id for i in range(20)}
    assert len(ids) >= 3


def test_body_never_thin_even_if_preferred_regular() -> None:
    from agents.marketing_agents.overlay_text import _FONTS_DIR, resolve_font_roles

    regular = _FONTS_DIR / "Montserrat-Regular.ttf"
    roles = resolve_font_roles(
        font_seed="feed-test",
        preferred_font_paths=[str(regular)] if regular.is_file() else None,
        prefer_script_display=False,
    )
    stem = Path(roles.body).stem.lower()
    assert "regular" not in stem
    assert any(w in stem for w in ("bold", "black", "heavy", "anton", "bebas", "archivo"))


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
