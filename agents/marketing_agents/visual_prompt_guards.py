"""Fragmentos de prompt compartidos: el modelo solo genera foto; tipografía = Pillow."""

from __future__ import annotations

# Sufijo obligatorio en prompts positivos (Fal / Venice / SD).
# Por defecto enfatiza atmósfera/producto, pero NO prohíbe personas.
NO_TEXT_PHOTO_SUFFIX = (
    "Single full-bleed photograph of the product, place, atmosphere, or people in the scene. "
    "Absolutely no text, no letters, no words, no logos, no watermarks, no signatures, "
    "no brand manuals, no color palette swatches, no UI mockups, no dashboards, "
    "no collages, no multi-panel layouts, no mood boards, no typography, no posters with copy."
)

# Cuando la revisión pide personas, el sufijo no debe empujar a "solo atmósfera vacía".
NO_TEXT_PHOTO_SUFFIX_WITH_PEOPLE = (
    "Single full-bleed photorealistic photograph that INCLUDES the requested people "
    "(e.g. a couple seated at the table). Empty chairs without people are wrong. "
    "Absolutely no text, no letters, no words, no logos, no watermarks, no signatures, "
    "no brand manuals, no color palette swatches, no UI mockups, no dashboards, "
    "no collages, no multi-panel layouts, no mood boards, no typography, no posters with copy."
)

# Negative prompt alineado (SD / Venice pixel models).
NO_TEXT_NEGATIVE = (
    "text, letters, words, watermark, signature, logo, brand manual, color palette, "
    "swatches, collage, multi-panel, mood board, UI mockup, dashboard, typography, "
    "poster layout, newspaper, magazine spread, blurry, low quality, deformed, ugly"
)

NO_TEXT_NEGATIVE_WITH_PEOPLE = (
    NO_TEXT_NEGATIVE
    + ", empty chairs, vacant table, deserted scene, no people, abandoned restaurant"
)


def with_photo_only_guard(prompt: str, *, allow_people: bool = False) -> str:
    """Asegura el sufijo anti-texto/anti-collage al final del prompt."""
    base = (prompt or "").strip()
    suffix = NO_TEXT_PHOTO_SUFFIX_WITH_PEOPLE if allow_people else NO_TEXT_PHOTO_SUFFIX
    if allow_people:
        already = "includes the requested people" in base.lower()
    else:
        already = "full-bleed photograph" in base.lower() and "no brand manuals" in base.lower()
    if already:
        return base
    if not base:
        return suffix
    return f"{base} {suffix}"
