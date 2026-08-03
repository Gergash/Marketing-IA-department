"""Extracción estructurada de señales visuales desde el manual de marca (prioridad máxima)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from .layout_archetypes import LayoutArchetype

# Colores nombrados frecuentes en brand books (ES/EN) → hex
_NAMED_COLORS: dict[str, str] = {
    "negro": "#111111",
    "black": "#111111",
    "blanco": "#FFFFFF",
    "white": "#FFFFFF",
    "rojo": "#E11D48",
    "red": "#E11D48",
    "azul": "#1D4ED8",
    "blue": "#1D4ED8",
    "navy": "#0F172A",
    "marino": "#0F172A",
    "verde": "#15803D",
    "green": "#15803D",
    "lima": "#84CC16",
    "lime": "#84CC16",
    "naranja": "#EA580C",
    "orange": "#EA580C",
    "amarillo": "#EAB308",
    "yellow": "#EAB308",
    "dorado": "#CA8A04",
    "gold": "#CA8A04",
    "morado": "#7C3AED",
    "púrpura": "#7C3AED",
    "purple": "#7C3AED",
    "rosa": "#DB2777",
    "pink": "#DB2777",
    "gris": "#6B7280",
    "gray": "#6B7280",
    "grey": "#6B7280",
    "teal": "#0D9488",
    "turquesa": "#14B8A6",
    "cyan": "#0891B2",
    "beige": "#D6C3A3",
    "crema": "#F5F0E6",
    "marrón": "#92400E",
    "brown": "#92400E",
    "coral": "#F97316",
}

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB_RE = re.compile(
    r"rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)",
    re.IGNORECASE,
)
_CMYK_RE = re.compile(
    r"cmyk\s*[:=\(]\s*(\d{1,3})\s*[,/\s]+\s*(\d{1,3})\s*[,/\s]+\s*(\d{1,3})\s*[,/\s]+\s*(\d{1,3})",
    re.IGNORECASE,
)
_PANTONE_RE = re.compile(
    r"pantone\s+(\d{2,4})\s*(?:c|u|m)?",
    re.IGNORECASE,
)
# Aproximaciones frecuentes Pantone → hex (subset brand-book)
_PANTONE_APPROX: dict[str, str] = {
    "186": "#C8102E",
    "485": "#DA291C",
    "286": "#0033A0",
    "287": "#003087",
    "300": "#005EB8",
    "348": "#00843D",
    "355": "#009639",
    "7466": "#00A3E0",
    "877": "#8A8D8F",
    "871": "#84754E",
}
_FONT_HINT_RE = re.compile(
    r"(?:fuente|tipograf[ií]a|font(?:[\s_-]?family)?|typeface|logotipo|wordmark)\s*[:\-]?\s*"
    r"([A-Za-z][A-Za-z0-9 \-]{1,40})",
    re.IGNORECASE,
)
_LOGO_MENTION_RE = re.compile(
    r"\b(logo|logotipo|isotipo|isologo|imagotipo|wordmark|monograma|s[ií]mbolo)\b",
    re.IGNORECASE,
)
_KNOWN_FONTS = (
    "montserrat",
    "poppins",
    "inter",
    "roboto",
    "raleway",
    "lato",
    "opensans",
    "open sans",
    "playfair",
    "georgia",
    "helvetica",
    "arial",
    "futura",
    "gotham",
    "proxima",
    "nunito",
    "oswald",
    "bebas",
    "impact",
    "segoe",
    "calibri",
    "verdana",
    "trebuchet",
    "courier",
    "times",
)
_EMOTION_WORDS = (
    "cercan",
    "calid",
    "cálid",
    "confianz",
    "premium",
    "lujo",
    "energet",
    "dinámic",
    "dinamíc",
    "innovador",
    "moderno",
    "minimal",
    "sofisticad",
    "alegre",
    "seren",
    "profesion",
    "disruptiv",
    "audaz",
    "bold",
    "warm",
    "friendly",
    "luxury",
    "playful",
    "tech",
    "human",
    "inspirador",
    "aspiracional",
)

_WINDOWS_FONTS = Path("C:/Windows/Fonts")


@dataclass
class BrandVisualCues:
    """Señales visuales del manual: colores, tipografías, logos, emociones y estilo."""

    primary_hex: str | None = None
    secondary_hex: str | None = None
    accent_hex: str | None = None
    palette_hex: list[str] = field(default_factory=list)
    font_names: list[str] = field(default_factory=list)
    emotions: list[str] = field(default_factory=list)
    style_keywords: list[str] = field(default_factory=list)
    client_imagery: str = ""
    logo_urls: list[str] = field(default_factory=list)
    logo_paths: list[str] = field(default_factory=list)
    logo_mentions: bool = False
    has_signal: bool = False


def parse_brand_visual_cues(brand_text: str) -> BrandVisualCues:
    """Parsea heurístico del texto del manual (sin LLM)."""
    text = (brand_text or "").strip()
    if len(text) < 20:
        return BrandVisualCues()

    hexes = [_normalize_hex(h) for h in _HEX_RE.findall(text)]
    for m in _RGB_RE.finditer(text):
        r, g, b = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if max(r, g, b) <= 255:
            hexes.append(f"#{r:02X}{g:02X}{b:02X}")
    for m in _CMYK_RE.finditer(text):
        c, m_, y, k = (int(m.group(i)) / 100.0 for i in range(1, 5))
        r = int(255 * (1 - c) * (1 - k))
        g = int(255 * (1 - m_) * (1 - k))
        b = int(255 * (1 - y) * (1 - k))
        hexes.append(f"#{r:02X}{g:02X}{b:02X}")
    for m in _PANTONE_RE.finditer(text):
        code = m.group(1)
        if code in _PANTONE_APPROX:
            hexes.append(_PANTONE_APPROX[code])

    lower = text.lower()
    for name, hx in _NAMED_COLORS.items():
        if re.search(rf"\b{re.escape(name)}\b", lower):
            # Solo si aparece cerca de “color/paleta/primario”
            # (evita “blanco” genérico en prosa); aún así lo agregamos como candidato.
            hexes.append(hx)

    # Dedup preservando orden
    seen: set[str] = set()
    unique_hexes: list[str] = []
    for h in hexes:
        if h and h not in seen:
            seen.add(h)
            unique_hexes.append(h)

    fonts: list[str] = []
    for m in _FONT_HINT_RE.finditer(text):
        name = m.group(1).strip(" .,;:-")
        if len(name) >= 3 and name.lower() not in {
            "logo", "logotipo", "isotipo", "isologo", "imagotipo", "wordmark", "monograma",
        }:
            fonts.append(name)
    for known in _KNOWN_FONTS:
        if known in lower and known.title() not in fonts:
            fonts.append(known.title() if " " not in known else known)

    emotions: list[str] = []
    for word in _EMOTION_WORDS:
        if word in lower:
            emotions.append(word.rstrip("aáeéoó").rstrip())

    style_keywords: list[str] = []
    for kw in (
        "minimalista",
        "editorial",
        "cinemático",
        "cinematic",
        "fotográfico",
        "ilustración",
        "flat",
        "3d",
        "neón",
        "neon",
        "orgánico",
        "industrial",
        "lujo",
        "street",
        "corporativo",
    ):
        if kw in lower:
            style_keywords.append(kw)

    primary = unique_hexes[0] if unique_hexes else None
    accent = unique_hexes[1] if len(unique_hexes) > 1 else primary
    secondary = unique_hexes[2] if len(unique_hexes) > 2 else (
        "#FFFFFF" if primary and primary.upper() not in {"#FFFFFF", "#FFF"} else "#111111"
    )

    imagery = _client_imagery_hint(text)
    logo_mentions = bool(_LOGO_MENTION_RE.search(text))
    has_signal = bool(primary or fonts or emotions or style_keywords or imagery or logo_mentions)

    return BrandVisualCues(
        primary_hex=primary,
        secondary_hex=secondary,
        accent_hex=accent,
        palette_hex=unique_hexes[:8],
        font_names=fonts[:5],
        emotions=list(dict.fromkeys(emotions))[:8],
        style_keywords=list(dict.fromkeys(style_keywords))[:6],
        client_imagery=imagery,
        logo_mentions=logo_mentions,
        has_signal=has_signal,
    )


def merge_scanned_assets(cues: BrandVisualCues, assets: dict | None) -> BrandVisualCues:
    """Fusiona paleta/logos del escaneo visual OCR+raster sobre cues de texto."""
    if not assets:
        return cues
    palette = [c.upper() if c.startswith("#") else c for c in (assets.get("palette_hex") or [])]
    logo_urls = list(assets.get("logo_urls") or [])
    logo_paths = list(assets.get("logo_paths") or [])

    # Paleta escaneada primero (colores reales del PDF); hex/nombres del texto como respaldo
    text_palette = list(cues.palette_hex or [])
    merged_palette: list[str] = []
    for hx in palette + text_palette:
        hx = hx.upper() if hx.startswith("#") else hx
        if hx and hx not in merged_palette:
            merged_palette.append(hx)

    if palette:
        # Escaneo visual manda: evita que "verde"/"azul" en prosa pisen el brand book
        primary = palette[0]
        accent = palette[1] if len(palette) > 1 else (cues.accent_hex or primary)
        secondary = palette[2] if len(palette) > 2 else (
            cues.secondary_hex
            or ("#FFFFFF" if primary.upper() not in {"#FFFFFF", "#FFF"} else "#111111")
        )
    else:
        primary = cues.primary_hex
        accent = cues.accent_hex
        secondary = cues.secondary_hex
        if not primary and merged_palette:
            primary = merged_palette[0]
            accent = merged_palette[1] if len(merged_palette) > 1 else primary
            secondary = merged_palette[2] if len(merged_palette) > 2 else (
                "#FFFFFF" if primary.upper() not in {"#FFFFFF", "#FFF"} else "#111111"
            )

    has_signal = cues.has_signal or bool(merged_palette or logo_urls or logo_paths)
    return replace(
        cues,
        primary_hex=primary,
        secondary_hex=secondary,
        accent_hex=accent or primary,
        palette_hex=merged_palette[:8],
        logo_urls=logo_urls,
        logo_paths=logo_paths,
        has_signal=has_signal,
    )


def resolve_brand_cues(
    brand_text: str,
    *,
    tenant_id: str | None = None,
    assets: dict | None = None,
) -> BrandVisualCues:
    """Parse texto + escaneo visual del tenant (si hay)."""
    cues = parse_brand_visual_cues(brand_text)
    if assets is None and tenant_id:
        try:
            from .brand_manual import load_brand_visual_assets

            assets = load_brand_visual_assets(tenant_id)
        except Exception:
            assets = None
    return merge_scanned_assets(cues, assets)


def apply_brand_to_archetype(archetype: LayoutArchetype, cues: BrandVisualCues) -> LayoutArchetype:
    """Sobrescribe colores del arquetipo con el manual (prioridad máxima)."""
    if not cues.has_signal:
        return archetype
    return replace(
        archetype,
        primary_hex=cues.primary_hex or archetype.primary_hex,
        secondary_hex=cues.secondary_hex or archetype.secondary_hex,
        accent_hex=cues.accent_hex or cues.primary_hex or archetype.accent_hex,
        flux_style=_brand_flux_style(archetype, cues),
        flux_composition=archetype.flux_composition,
    )


def brand_priority_prompt_block(cues: BrandVisualCues, brand_text: str = "") -> str:
    """Bloque obligatorio al inicio del prompt de imagen."""
    if not cues.has_signal and not (brand_text or "").strip():
        return ""
    parts = [
        "BRAND MANUAL — HIGHEST PRIORITY (override generic agency defaults; "
        "DO NOT default to yellow/white poster look unless the brand specifies it):"
    ]
    palette = cues.palette_hex or [
        c for c in (cues.primary_hex, cues.secondary_hex, cues.accent_hex) if c
    ]
    if palette:
        parts.append(f"Exact brand color palette (use these hexes): {', '.join(palette)}.")
    if cues.primary_hex or cues.accent_hex:
        parts.append(
            f"Brand roles: primary {cues.primary_hex or 'n/a'}, "
            f"secondary {cues.secondary_hex or 'n/a'}, accent {cues.accent_hex or 'n/a'}."
        )
    if cues.font_names:
        parts.append(
            f"Typography vibe inspired by: {', '.join(cues.font_names)} "
            "(no readable letters in the image)."
        )
    if cues.logo_paths or cues.logo_urls or cues.logo_mentions:
        parts.append(
            "Official brand logo will be composited in post — leave clean corner space; "
            "do NOT invent or redraw any logo mark, letters, or wordmark."
        )
    if cues.emotions:
        parts.append(f"Emotional tone: {', '.join(cues.emotions)}.")
    if cues.style_keywords:
        parts.append(f"Visual style: {', '.join(cues.style_keywords)}.")
    if cues.client_imagery:
        parts.append(f"Client-specific imagery: {cues.client_imagery}")
    excerpt = (brand_text or "").strip()
    if excerpt:
        clip = excerpt[:900].replace("\n", " ")
        parts.append(f"Brand guidelines excerpt: {clip}")
    parts.append(
        "Imagery only: full-bleed real photography of the client's product/place/atmosphere. "
        "Typography and logo are composited in post — do NOT paint letters, brand manuals, "
        "color swatches, collages, or multi-panel layouts."
    )
    return " ".join(parts)


def resolve_brand_font_paths(font_names: list[str], brand_text: str = "") -> list[str]:
    """
    Mapea tipografías del manual a TTF.

    Orden: pack OFL del proyecto (script/sans si el texto habla de caligrafía) →
    Windows Fonts por nombre → pack como fallback.
    """
    from .overlay_text import pack_font_roles

    found: list[str] = []
    pack = pack_font_roles()
    lower = (brand_text or "").lower()
    wants_script = any(
        k in lower
        for k in (
            "caligr",
            "calligr",
            "script",
            "cursiva",
            "handwrit",
            "manuscrit",
            "great vibes",
            "playfair",
        )
    )
    wants_sans = any(
        k in lower for k in ("sans", "montserrat", "helvetica", "arial", "grotesk", "limpia")
    )

    if pack:
        if wants_script or not font_names:
            found.append(pack.display)
        if wants_sans or wants_script or not font_names:
            found.append(pack.body)
            found.append(pack.cta)
        if pack.tagline not in found:
            found.append(pack.tagline)

    # Nombres explícitos del manual → Windows
    if font_names and _WINDOWS_FONTS.is_dir():
        available = list(_WINDOWS_FONTS.glob("*.ttf")) + list(_WINDOWS_FONTS.glob("*.otf"))
        for name in font_names:
            key = re.sub(r"[^a-z0-9]", "", name.lower())
            if key in {"script", "caligrafico", "caligráfico", "calligraphy", "handwriting"}:
                if pack and pack.display not in found:
                    found.insert(0, pack.display)
                continue
            bold_hits = [
                p
                for p in available
                if key in re.sub(r"[^a-z0-9]", "", p.stem.lower())
                and any(b in p.stem.lower() for b in ("bd", "bold", "black", "heavy"))
            ]
            regular_hits = [
                p for p in available if key in re.sub(r"[^a-z0-9]", "", p.stem.lower())
            ]
            for hit in bold_hits + regular_hits:
                path = str(hit)
                if path not in found:
                    found.append(path)
                if len(found) >= 6:
                    break

    # Dedup preservando orden
    out: list[str] = []
    for p in found:
        if p and p not in out:
            out.append(p)
    if not out and pack:
        return [pack.display, pack.body, pack.cta, pack.tagline]
    return out[:6]


def extract_brand_name_candidates(brand_text: str, tema: str = "") -> list[str]:
    """Heurística: nombres de marca para resaltar en el overlay (p. ej. Tres Amores)."""
    names: list[str] = []
    text = brand_text or ""
    for pat in (
        r"(?i)marca\s*:\s*([^\n·|]{2,40})",
        r"(?i)brand\s*:\s*([^\n·|]{2,40})",
        r"(?i)^([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ]+){0,3})\s+Café",
    ):
        for m in re.finditer(pat, text):
            cand = m.group(1).strip(" .,-")
            # Quitar sufijos tipo "Café • Bar"
            cand = re.split(r"\s*[•|·]\s*", cand)[0].strip()
            if 2 <= len(cand) <= 40 and cand.lower() not in {"una", "el", "la"}:
                names.append(cand)
    # Del tema: "… en Tres Amores"
    if tema:
        m = re.search(r"(?i)\ben\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ]+)?)", tema)
        if m:
            names.append(m.group(1).strip())
    # Dedup
    out: list[str] = []
    for n in names:
        if n not in out:
            out.append(n)
    return out[:5]

def _normalize_hex(h: str) -> str:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"#{h.upper()}"


def _brand_flux_style(archetype: LayoutArchetype, cues: BrandVisualCues) -> str:
    bits = [archetype.flux_style]
    if cues.style_keywords:
        bits.append("brand style " + ", ".join(cues.style_keywords))
    if cues.emotions:
        bits.append("mood " + ", ".join(cues.emotions[:4]))
    if cues.primary_hex:
        bits.append(f"dominant brand color {cues.primary_hex}")
    return "; ".join(bits)


def _client_imagery_hint(text: str) -> str:
    """Extrae una pista de imagery del inicio del manual (producto/servicio)."""
    # Primera frase sustancial
    cleaned = re.sub(r"\s+", " ", text.strip())
    for sep in (". ", ".\n", "\n\n"):
        if sep in cleaned[:500]:
            first = cleaned.split(sep, 1)[0].strip()
            if 40 <= len(first) <= 280:
                return first
    return cleaned[:220]
