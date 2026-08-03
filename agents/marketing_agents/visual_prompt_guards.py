"""Fragmentos de prompt compartidos: el modelo solo genera foto; tipografía = Pillow."""

from __future__ import annotations

# Sufijo obligatorio en prompts positivos (Fal / Venice / SD).
NO_TEXT_PHOTO_SUFFIX = (
    "Single full-bleed photograph of the product, place, or atmosphere only. "
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


def with_photo_only_guard(prompt: str) -> str:
    """Asegura el sufijo anti-texto/anti-collage al final del prompt."""
    base = (prompt or "").strip()
    if "no brand manuals" in base.lower() and "full-bleed photograph" in base.lower():
        return base
    if not base:
        return NO_TEXT_PHOTO_SUFFIX
    return f"{base} {NO_TEXT_PHOTO_SUFFIX}"
