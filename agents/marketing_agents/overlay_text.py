"""Texto y tipografía para overlay sobre imágenes generadas."""

from __future__ import annotations

import re
import textwrap


def truncate_at_sentence(text: str, max_chars: int) -> str:
    """Recorta en límite de oración para evitar palabras cortadas (p. ej. 'intelige')."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text or len(text) <= max_chars:
        return text
    window = text[:max_chars]
    for sep in (". ", "? ", "! ", "; ", ", "):
        idx = window.rfind(sep)
        if idx >= int(max_chars * 0.35):
            return window[: idx + len(sep.rstrip())].strip()
    idx = window.rfind(" ")
    if idx > 0:
        return window[:idx].rstrip() + "…"
    return window.rstrip() + "…"


def build_overlay_lines(
    *,
    headline: str,
    subline: str | None = None,
    max_headline_chars: int = 100,
    max_subline_chars: int = 80,
) -> tuple[str, str | None]:
    """Prepara headline y subline completos para el overlay."""
    h = truncate_at_sentence(headline, max_headline_chars)
    s = truncate_at_sentence(subline, max_subline_chars) if subline else None
    if s and s == h:
        s = None
    return h, s


def wrap_for_width(text: str, pixel_width: int, *, font_size: int) -> str:
    """Envuelve texto según ancho útil de la imagen (aprox. caracteres por línea)."""
    chars_per_line = max(18, int(pixel_width / max(font_size * 0.55, 1)))
    return textwrap.fill(text, width=chars_per_line)


# Pares tipográficos (Windows): título + cuerpo/CTA — rota por hash de plataforma
_FONT_PAIRS: list[tuple[tuple[str, int], tuple[str, int]]] = [
    (("C:/Windows/Fonts/segoeuib.ttf", 0), ("C:/Windows/Fonts/segoeui.ttf", 0)),
    (("C:/Windows/Fonts/calibrib.ttf", 0), ("C:/Windows/Fonts/calibri.ttf", 0)),
    (("C:/Windows/Fonts/georgiab.ttf", 0), ("C:/Windows/Fonts/georgia.ttf", 0)),
    (("C:/Windows/Fonts/arialbd.ttf", 0), ("C:/Windows/Fonts/arial.ttf", 0)),
    (("C:/Windows/Fonts/impact.ttf", 0), ("C:/Windows/Fonts/arial.ttf", 0)),
    (("C:/Windows/Fonts/verdana.ttf", 0), ("C:/Windows/Fonts/verdanab.ttf", 0)),
    (("C:/Windows/Fonts/tahoma.ttf", 0), ("C:/Windows/Fonts/tahomabd.ttf", 0)),
]


def pick_font_pair(
    seed: str,
    base_size: int,
    *,
    preferred_font_paths: list[str] | None = None,
) -> tuple[tuple[str, int], tuple[str, int]]:
    """Elige par de fuentes: preferencia del manual de marca > seed de plataforma."""
    paths = [p for p in (preferred_font_paths or []) if p]
    if paths:
        title = paths[0]
        body = paths[1] if len(paths) > 1 else paths[0]
        return (title, base_size + 4), (body, base_size)
    idx = sum(ord(c) for c in seed) % len(_FONT_PAIRS)
    title_path, _ = _FONT_PAIRS[idx][0]
    body_path, _ = _FONT_PAIRS[idx][1]
    return (title_path, base_size + 2), (body_path, base_size)
