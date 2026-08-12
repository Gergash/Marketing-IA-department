"""Tests: parseo de señales visuales del manual de marca y prioridad en prompts."""

from __future__ import annotations

from agents.marketing_agents.brand_visual import (
    apply_brand_to_archetype,
    brand_priority_prompt_block,
    parse_brand_visual_cues,
)
from agents.marketing_agents.image_specs import resolve_image_spec
from agents.marketing_agents.layout_archetypes import (
    _ARCHETYPE_MAP,
    build_flux_prompt,
)
from agents.marketing_agents.schemas import BriefInput, StrategyOutput


def test_parse_brand_visual_cues_hex_fonts_emotions() -> None:
    text = """
    Manual de marca Acme IoT.
    Colores primarios: #0F766E y #111827. Acento #F97316.
    Tipografía: Montserrat Bold y fuente: Calibri.
    Tono: cercano, premium, innovador y profesional.
    Estilo minimalista editorial.
    """
    cues = parse_brand_visual_cues(text)
    assert cues.has_signal
    assert cues.primary_hex == "#0F766E"
    assert cues.accent_hex in {"#111827", "#F97316"}
    assert any("montserrat" in f.lower() or "calibri" in f.lower() for f in cues.font_names)
    assert cues.emotions
    assert "minimalista" in cues.style_keywords or "editorial" in cues.style_keywords


def test_apply_brand_overrides_yellow_defaults() -> None:
    base = _ARCHETYPE_MAP["typographic_poster"]
    cues = parse_brand_visual_cues("Paleta #1D4ED8 primario, acento #F59E0B. Emoción cálida premium.")
    patched = apply_brand_to_archetype(base, cues)
    assert patched.primary_hex == "#1D4ED8"
    assert patched.accent_hex in {"#1D4ED8", "#F59E0B"}
    assert patched.primary_hex != "#FFE500"


def test_build_flux_prompt_puts_brand_first() -> None:
    brief = BriefInput(
        tema="Cámaras IoT para barrios",
        publico_objetivo="alcaldías",
        red_social="instagram",
        objetivo="branding",
        tono_marca="cercano",
        brand_context=(
            "Brand book. Primary #0F766E. Font Montserrat. "
            "Emoción confiable e innovadora. Estilo fotográfico cinematográfico."
        ),
    )
    strategy = StrategyOutput(
        tipo_post="educativo",
        hook="Seguridad inteligente",
        mensaje_base="IoT que cuida tu ciudad",
        hashtags=["#IoT"],
    )
    archetype = apply_brand_to_archetype(
        _ARCHETYPE_MAP["editorial_infographic"],
        parse_brand_visual_cues(brief.brand_context),
    )
    prompt = build_flux_prompt(
        archetype,
        brief=brief,
        strategy=strategy,
        spec=resolve_image_spec("instagram", "feed"),
    )
    assert prompt.startswith("BRAND MANUAL")
    assert "#0F766E" in prompt
    assert "HIGHEST PRIORITY" in prompt
    assert "yellow" in prompt.lower()  # instrucción de evitar yellow genérico


def test_brand_priority_block_empty_without_signal() -> None:
    assert brand_priority_prompt_block(parse_brand_visual_cues(""), "") == ""
