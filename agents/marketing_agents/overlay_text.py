"""Texto y tipografía para overlay sobre imágenes generadas."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

_FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"

# Pack empaquetado (OFL) — roles fijos para piezas tipo ChatGPT / brand campaign
_PACK_DISPLAY = _FONTS_DIR / "GreatVibes-Regular.ttf"
_PACK_SERIF = _FONTS_DIR / "PlayfairDisplay-Regular.ttf"
_PACK_BODY = _FONTS_DIR / "Montserrat-Regular.ttf"
_PACK_CTA = _FONTS_DIR / "Montserrat-Bold.ttf"

# Pares tipográficos Windows (fallback si falta el pack)
_FONT_PAIRS: list[tuple[tuple[str, int], tuple[str, int]]] = [
    (("C:/Windows/Fonts/segoeuib.ttf", 0), ("C:/Windows/Fonts/segoeui.ttf", 0)),
    (("C:/Windows/Fonts/calibrib.ttf", 0), ("C:/Windows/Fonts/calibri.ttf", 0)),
    (("C:/Windows/Fonts/georgiab.ttf", 0), ("C:/Windows/Fonts/georgia.ttf", 0)),
    (("C:/Windows/Fonts/arialbd.ttf", 0), ("C:/Windows/Fonts/arial.ttf", 0)),
    (("C:/Windows/Fonts/impact.ttf", 0), ("C:/Windows/Fonts/arial.ttf", 0)),
    (("C:/Windows/Fonts/verdana.ttf", 0), ("C:/Windows/Fonts/verdanab.ttf", 0)),
    (("C:/Windows/Fonts/tahoma.ttf", 0), ("C:/Windows/Fonts/tahomabd.ttf", 0)),
]


@dataclass(frozen=True)
class FontRoles:
    """Rutas TTF por rol tipográfico (display script, body sans, CTA, tagline serif)."""

    display: str
    body: str
    cta: str
    tagline: str


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


def _existing(path: Path | str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    return str(p) if p.is_file() else None


def pack_font_roles() -> FontRoles | None:
    """Devuelve el pack OFL del repo si los cuatro archivos existen."""
    display = _existing(_PACK_DISPLAY)
    serif = _existing(_PACK_SERIF)
    body = _existing(_PACK_BODY)
    cta = _existing(_PACK_CTA) or body
    if display and body and cta:
        return FontRoles(
            display=display,
            body=body,
            cta=cta,
            tagline=serif or display,
        )
    return None


def resolve_font_roles(
    *,
    font_seed: str = "instagram",
    preferred_font_paths: list[str] | None = None,
    prefer_script_display: bool = True,
) -> FontRoles:
    """
    Resuelve display / body / cta / tagline.

    Prioridad: pack del proyecto (script+sans) > preferred del manual > Windows.
    """
    pack = pack_font_roles()
    preferred = [p for p in (preferred_font_paths or []) if _existing(p)]

    if pack and prefer_script_display:
        # Manual puede aportar un sans/serif; el display script del pack manda en headline
        body = preferred[0] if preferred else pack.body
        # Si el preferred parece bold/sans, usarlo como body; CTA = bold pack
        cta = pack.cta
        tagline = pack.tagline
        if len(preferred) >= 2:
            body = preferred[1] if _looks_sans(preferred[1]) else preferred[0]
        return FontRoles(
            display=pack.display,
            body=body if _existing(body) else pack.body,
            cta=cta,
            tagline=tagline,
        )

    if preferred:
        title = preferred[0]
        body = preferred[1] if len(preferred) > 1 else preferred[0]
        return FontRoles(display=title, body=body, cta=body, tagline=title)

    if pack:
        return pack

    idx = sum(ord(c) for c in (font_seed or "")) % len(_FONT_PAIRS)
    title_path, _ = _FONT_PAIRS[idx][0]
    body_path, _ = _FONT_PAIRS[idx][1]
    return FontRoles(
        display=title_path,
        body=body_path,
        cta=title_path,
        tagline=body_path,
    )


def _looks_sans(path: str) -> bool:
    name = Path(path).stem.lower()
    return any(k in name for k in ("montserrat", "segoe", "arial", "calibri", "verdana", "tahoma", "sans"))


def pick_font_pair(
    seed: str,
    base_size: int,
    *,
    preferred_font_paths: list[str] | None = None,
) -> tuple[tuple[str, int], tuple[str, int]]:
    """Compat: par título+cuerpo. Preferir ``resolve_font_roles`` en layouts nuevos."""
    roles = resolve_font_roles(
        font_seed=seed,
        preferred_font_paths=preferred_font_paths,
        prefer_script_display=False,
    )
    return (roles.display, base_size + 4), (roles.body, base_size)


def split_brand_highlight(text: str, brand_names: list[str] | None = None) -> list[tuple[str, bool]]:
    """
    Parte el texto en segmentos (texto, es_marca).
    Resalta coincidencias case-insensitive de nombres de marca.
    """
    if not text:
        return []
    names = [n.strip() for n in (brand_names or []) if n and len(n.strip()) >= 2]
    if not names:
        return [(text, False)]
    # Ordenar por longitud desc para matchear "Tres Amores" antes que "Amores"
    names = sorted(names, key=len, reverse=True)
    pattern = "|".join(re.escape(n) for n in names)
    parts: list[tuple[str, bool]] = []
    last = 0
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        if m.start() > last:
            parts.append((text[last : m.start()], False))
        parts.append((m.group(0), True))
        last = m.end()
    if last < len(text):
        parts.append((text[last:], False))
    return parts or [(text, False)]
