"""Pruebas de arquetipos de layout y dimensiones de imagen."""

from agents.marketing_agents.image_specs import fal_image_size_arg, resolve_image_spec
from agents.marketing_agents.layout_archetypes import (
    ARCHETYPES,
    build_flux_prompt,
    pick_archetype,
)
from agents.marketing_agents.schemas import BriefInput, StrategyOutput


def test_instagram_feed_is_portrait_4_5() -> None:
    spec = resolve_image_spec("instagram", "feed")
    assert spec.width == 1080
    assert spec.height == 1350


def test_fal_image_size_scales_story() -> None:
    story = resolve_image_spec("instagram", "story")
    size = fal_image_size_arg(story)
    assert size["height"] <= 1440
    assert size["width"] <= 1440
    assert size["height"] % 8 == 0
    assert size["width"] % 8 == 0
    ratio = size["width"] / size["height"]
    assert abs(ratio - (1080 / 1920)) < 0.02


def test_pick_archetype_by_post_type() -> None:
    brief = BriefInput(
        tema="marketing digital",
        publico_objetivo="pymes",
        red_social="instagram",
        objetivo="ventas",
    )
    promo = StrategyOutput(
        tipo_post="promocional",
        hook="h",
        mensaje_base="m",
        hashtags=["#a"],
    )
    assert pick_archetype(brief, promo).id == "typographic_poster"

    edu = StrategyOutput(
        tipo_post="educativo",
        hook="h",
        mensaje_base="m",
        hashtags=["#a"],
    )
    assert pick_archetype(brief, edu).id == "editorial_infographic"


def test_build_flux_prompt_no_text_in_image() -> None:
    brief = BriefInput(
        tema="automatizacion",
        publico_objetivo="equipos",
        red_social="instagram",
        objetivo="branding",
    )
    strategy = StrategyOutput(
        tipo_post="informativo",
        hook="hook",
        mensaje_base="msg",
        hashtags=[],
    )
    archetype = pick_archetype(brief, strategy)
    prompt = build_flux_prompt(archetype, brief=brief, strategy=strategy, spec=resolve_image_spec("instagram", "feed"))
    assert "no text" in prompt.lower()
    assert archetype.id in ARCHETYPES
