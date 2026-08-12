"""Texto y tipografía para overlay sobre imágenes generadas.

Catálogo multi-familia (OFL en ``static/fonts``). Los subtítulos / body
siempre usan pesos gruesos (Bold / ExtraBold / Black) — nunca Regular/Light.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

_FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"

# Tokens de peso delgado / regular que NO deben usarse bajo títulos
_THIN_TOKENS = (
    "thin",
    "hairline",
    "extralight",
    "extra-light",
    "ultralight",
    "light",
    "regular",
    "book",
    "medium",
    "semibold",
    "semi-bold",
    "demibold",
)

# Pesos aceptados para body / subtítulo / CTA
_BOLD_TOKENS = ("bold", "extrabold", "extra-bold", "black", "heavy", "ultrabold", "fat")


@dataclass(frozen=True)
class FontFamily:
    """Una familia tipográfica con rutas por rol (solo archivos existentes)."""

    id: str
    title: str  # headline
    body: str  # subtítulo — siempre grueso
    cta: str
    tagline: str
    style: str  # script | display | sans | serif


@dataclass(frozen=True)
class FontRoles:
    """Rutas TTF por rol tipográfico."""

    display: str
    body: str
    cta: str
    tagline: str
    family_id: str = ""


def _p(name: str) -> Path:
    return _FONTS_DIR / name


def _existing(path: Path | str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    return str(p) if p.is_file() else None


def _is_thin_filename(path: str | Path) -> bool:
    stem = Path(path).stem.lower().replace(" ", "")
    # Anton/Bebas/ArchivoBlack son display gruesos aunque digan Regular
    if any(k in stem for k in ("anton", "bebas", "archivoblack", "impact")):
        return False
    if any(t in stem for t in _BOLD_TOKENS):
        return False
    if any(t in stem for t in _THIN_TOKENS):
        return True
    # Sin indicador de peso → tratar como regular (no usar en body)
    return True


def _is_bold_filename(path: str | Path) -> bool:
    stem = Path(path).stem.lower().replace(" ", "")
    if any(k in stem for k in ("anton", "bebas", "archivoblack", "impact", "black")):
        return True
    return any(t in stem for t in _BOLD_TOKENS)


def _first_existing(*names: str) -> str | None:
    for name in names:
        hit = _existing(_p(name))
        if hit:
            return hit
    return None


def _build_catalog() -> list[FontFamily]:
    """Familias disponibles en disco (se omiten las incompletas)."""
    specs: list[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], str]] = [
        # id, style, title candidates, body (bold), cta, tagline
        (
            "montserrat",
            "sans",
            ("Montserrat-Black.ttf", "Montserrat-ExtraBold.ttf", "Montserrat-Bold.ttf"),
            ("Montserrat-ExtraBold.ttf", "Montserrat-Bold.ttf", "Montserrat-Black.ttf"),
            ("Montserrat-Black.ttf", "Montserrat-ExtraBold.ttf", "Montserrat-Bold.ttf"),
            ("Montserrat-Bold.ttf", "Montserrat-ExtraBold.ttf"),
            "sans",
        ),
        (
            "poppins",
            "sans",
            ("Poppins-Black.ttf", "Poppins-ExtraBold.ttf", "Poppins-Bold.ttf"),
            ("Poppins-Bold.ttf", "Poppins-ExtraBold.ttf", "Poppins-Black.ttf"),
            ("Poppins-ExtraBold.ttf", "Poppins-Black.ttf", "Poppins-Bold.ttf"),
            ("Poppins-Bold.ttf", "Poppins-ExtraBold.ttf"),
            "sans",
        ),
        (
            "barlow",
            "sans",
            ("Barlow-Black.ttf", "Barlow-ExtraBold.ttf", "Barlow-Bold.ttf"),
            ("Barlow-Bold.ttf", "Barlow-ExtraBold.ttf", "Barlow-Black.ttf"),
            ("Barlow-Black.ttf", "Barlow-ExtraBold.ttf"),
            ("Barlow-Bold.ttf",),
            "sans",
        ),
        (
            "rubik",
            "sans",
            ("Rubik-Black.ttf", "Rubik-ExtraBold.ttf", "Rubik-Bold.ttf"),
            ("Rubik-Bold.ttf", "Rubik-ExtraBold.ttf", "Rubik-Black.ttf"),
            ("Rubik-ExtraBold.ttf", "Rubik-Black.ttf"),
            ("Rubik-Bold.ttf",),
            "sans",
        ),
        (
            "nunito",
            "sans",
            ("Nunito-Black.ttf", "Nunito-ExtraBold.ttf", "Nunito-Bold.ttf"),
            ("Nunito-Bold.ttf", "Nunito-ExtraBold.ttf", "Nunito-Black.ttf"),
            ("Nunito-ExtraBold.ttf", "Nunito-Black.ttf"),
            ("Nunito-Bold.ttf",),
            "sans",
        ),
        (
            "raleway",
            "sans",
            ("Raleway-Black.ttf", "Raleway-ExtraBold.ttf", "Raleway-Bold.ttf"),
            ("Raleway-Bold.ttf", "Raleway-ExtraBold.ttf", "Raleway-Black.ttf"),
            ("Raleway-ExtraBold.ttf", "Raleway-Black.ttf"),
            ("Raleway-Bold.ttf",),
            "sans",
        ),
        (
            "oswald",
            "display",
            ("Oswald-Bold.ttf", "ArchivoBlack-Regular.ttf", "Anton-Regular.ttf"),
            ("Oswald-Bold.ttf", "Montserrat-Bold.ttf", "Poppins-Bold.ttf"),
            ("Oswald-Bold.ttf", "Montserrat-ExtraBold.ttf"),
            ("Oswald-Bold.ttf", "Montserrat-Bold.ttf"),
            "display",
        ),
        (
            "anton",
            "display",
            ("Anton-Regular.ttf", "ArchivoBlack-Regular.ttf", "BebasNeue-Regular.ttf"),
            ("Montserrat-Bold.ttf", "Poppins-Bold.ttf", "Barlow-Bold.ttf"),
            ("Montserrat-ExtraBold.ttf", "Poppins-ExtraBold.ttf"),
            ("Montserrat-Bold.ttf", "RobotoSlab-Bold.ttf"),
            "display",
        ),
        (
            "bebas",
            "display",
            ("BebasNeue-Regular.ttf", "Anton-Regular.ttf", "ArchivoBlack-Regular.ttf"),
            ("Barlow-Bold.ttf", "Montserrat-Bold.ttf", "Poppins-Bold.ttf"),
            ("Barlow-ExtraBold.ttf", "Montserrat-Black.ttf"),
            ("Barlow-Bold.ttf",),
            "display",
        ),
        (
            "archivo_black",
            "display",
            ("ArchivoBlack-Regular.ttf", "Anton-Regular.ttf", "Oswald-Bold.ttf"),
            ("Montserrat-ExtraBold.ttf", "Poppins-Bold.ttf", "Rubik-Bold.ttf"),
            ("Montserrat-Black.ttf", "Poppins-Black.ttf"),
            ("RobotoSlab-Bold.ttf", "Montserrat-Bold.ttf"),
            "display",
        ),
        (
            "playfair",
            "serif",
            ("PlayfairDisplay-Black.ttf", "PlayfairDisplay-Bold.ttf"),
            ("RobotoSlab-Bold.ttf", "PlayfairDisplay-Bold.ttf", "Montserrat-Bold.ttf"),
            ("PlayfairDisplay-Black.ttf", "Montserrat-ExtraBold.ttf"),
            ("PlayfairDisplay-Bold.ttf", "RobotoSlab-Bold.ttf"),
            "serif",
        ),
        (
            "slab",
            "serif",
            ("RobotoSlab-Black.ttf", "RobotoSlab-Bold.ttf", "PlayfairDisplay-Bold.ttf"),
            ("RobotoSlab-Bold.ttf", "Montserrat-Bold.ttf", "Nunito-Bold.ttf"),
            ("RobotoSlab-Black.ttf", "Montserrat-ExtraBold.ttf"),
            ("RobotoSlab-Bold.ttf", "PlayfairDisplay-Bold.ttf"),
            "serif",
        ),
        (
            "script_campaign",
            "script",
            ("GreatVibes-Regular.ttf",),
            ("Montserrat-Bold.ttf", "Poppins-Bold.ttf", "Nunito-Bold.ttf"),
            ("Montserrat-ExtraBold.ttf", "Montserrat-Black.ttf", "Poppins-ExtraBold.ttf"),
            ("PlayfairDisplay-Bold.ttf", "PlayfairDisplay-Black.ttf", "RobotoSlab-Bold.ttf"),
            "script",
        ),
    ]

    families: list[FontFamily] = []
    for fid, _label, titles, bodies, ctas, tags, style in specs:
        title = _first_existing(*titles)
        body = _first_existing(*bodies)
        cta = _first_existing(*ctas) or body
        tag = _first_existing(*tags) or body
        if not (title and body and cta):
            continue
        # Guardrail: body y cta nunca delgados
        if _is_thin_filename(body):
            body = _first_existing(
                "Montserrat-Bold.ttf",
                "Poppins-Bold.ttf",
                "Barlow-Bold.ttf",
                "Rubik-Bold.ttf",
            )
        if not body or _is_thin_filename(body):
            continue
        if cta and _is_thin_filename(cta):
            cta = body
        families.append(
            FontFamily(id=fid, title=title, body=body, cta=cta or body, tagline=tag or body, style=style)
        )
    return families


_CATALOG: list[FontFamily] | None = None


def list_font_families() -> list[FontFamily]:
    """Catálogo vivo (relee disco si hace falta)."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = _build_catalog()
    return _CATALOG


def reload_font_catalog() -> list[FontFamily]:
    global _CATALOG
    _CATALOG = None
    return list_font_families()


def pack_font_roles() -> FontRoles | None:
    """Pack canónico de campaña (script + body grueso). Compat tests / brand_visual."""
    families = list_font_families()
    script = next((f for f in families if f.id == "script_campaign"), None)
    mont = next((f for f in families if f.id == "montserrat"), None)
    if script:
        return FontRoles(
            display=script.title,
            body=script.body,
            cta=script.cta,
            tagline=script.tagline,
            family_id=script.id,
        )
    if mont:
        return FontRoles(
            display=mont.title,
            body=mont.body,
            cta=mont.cta,
            tagline=mont.tagline,
            family_id=mont.id,
        )
    if families:
        f = families[0]
        return FontRoles(
            display=f.title, body=f.body, cta=f.cta, tagline=f.tagline, family_id=f.id
        )
    return None


def _seed_index(seed: str, n: int) -> int:
    if n <= 0:
        return 0
    return sum(ord(c) for c in (seed or "x")) % n


def pick_font_family(seed: str = "instagram", *, prefer_script: bool = False) -> FontFamily | None:
    """Elige una familia del catálogo según seed (variación entre imágenes)."""
    families = list_font_families()
    if not families:
        return None
    if prefer_script:
        scripts = [f for f in families if f.style == "script"]
        if scripts:
            return scripts[_seed_index(seed, len(scripts))]
    # Mezclar estilos: sans / display / serif (sin forzar siempre el mismo)
    pool = [f for f in families if f.style != "script"] or families
    return pool[_seed_index(seed, len(pool))]


def enforce_bold_path(path: str | None, *, fallback_family: FontFamily | None = None) -> str | None:
    """Si la ruta es delgada, sustituye por un Bold del catálogo."""
    if path and _existing(path) and not _is_thin_filename(path):
        return path
    if fallback_family and _existing(fallback_family.body):
        return fallback_family.body
    bold = _first_existing(
        "Montserrat-Bold.ttf",
        "Poppins-Bold.ttf",
        "Barlow-Bold.ttf",
        "Rubik-Bold.ttf",
        "Nunito-Bold.ttf",
        "Raleway-Bold.ttf",
    )
    return bold


def resolve_font_roles(
    *,
    font_seed: str = "instagram",
    preferred_font_paths: list[str] | None = None,
    prefer_script_display: bool = True,
) -> FontRoles:
    """
    Resuelve display / body / cta / tagline.

    - Varía la familia según ``font_seed`` (más de un tipo de fuente).
    - Body / subtítulo / CTA: siempre peso grueso.
    - preferred del manual se respeta si es Bold+; si es Regular se refuerza.
    """
    family = pick_font_family(font_seed, prefer_script=prefer_script_display)
    preferred = [p for p in (preferred_font_paths or []) if _existing(p)]

    if prefer_script_display:
        pack = pack_font_roles()
        if pack:
            body = pack.body
            # Preferidos del manual: solo si son gruesos
            for p in preferred:
                if not _is_thin_filename(p):
                    body = p
                    break
            body = enforce_bold_path(body, fallback_family=family) or pack.body
            cta = enforce_bold_path(pack.cta, fallback_family=family) or body
            return FontRoles(
                display=pack.display,
                body=body,
                cta=cta,
                tagline=enforce_bold_path(pack.tagline, fallback_family=family) or pack.tagline,
                family_id=pack.family_id,
            )

    if preferred and family:
        # Título: primer preferred (puede ser display/script)
        title = preferred[0]
        # Body: primer preferred grueso distinto del título, o body de familia
        body_cand = None
        for p in preferred[1:] + preferred[:1]:
            if not _is_thin_filename(p):
                body_cand = p
                break
        body = enforce_bold_path(body_cand, fallback_family=family) or family.body
        cta = enforce_bold_path(
            next((p for p in preferred if _is_bold_filename(p)), None),
            fallback_family=family,
        ) or family.cta
        return FontRoles(
            display=title,
            body=body,
            cta=cta,
            tagline=family.tagline,
            family_id=family.id,
        )

    if family:
        return FontRoles(
            display=family.title,
            body=family.body,
            cta=family.cta,
            tagline=family.tagline,
            family_id=family.id,
        )

    # Último recurso: Windows bold
    win = _windows_bold_pair(font_seed)
    return FontRoles(display=win[0], body=win[1], cta=win[0], tagline=win[1], family_id="windows")


def _windows_bold_pair(seed: str) -> tuple[str, str]:
    pairs = [
        ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("C:/Windows/Fonts/calibrib.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        ("C:/Windows/Fonts/verdanab.ttf", "C:/Windows/Fonts/verdanab.ttf"),
        ("C:/Windows/Fonts/tahomabd.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
        ("C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/georgiab.ttf"),
    ]
    existing = [(a, b) for a, b in pairs if Path(a).is_file() and Path(b).is_file()]
    if not existing:
        return "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"
    return existing[_seed_index(seed, len(existing))]


def pick_font_pair(
    seed: str,
    base_size: int,
    *,
    preferred_font_paths: list[str] | None = None,
) -> tuple[tuple[str, int], tuple[str, int]]:
    """Par título+cuerpo. El cuerpo siempre es Bold+ y la familia varía con seed."""
    roles = resolve_font_roles(
        font_seed=seed,
        preferred_font_paths=preferred_font_paths,
        prefer_script_display=False,
    )
    body = enforce_bold_path(roles.body) or roles.body
    return (roles.display, base_size + 4), (body, base_size)


def truncate_at_sentence(text: str, max_chars: int) -> str:
    """Recorta en límite de oración para evitar palabras cortadas."""
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
    """Envuelve texto según ancho útil de la imagen."""
    chars_per_line = max(18, int(pixel_width / max(font_size * 0.55, 1)))
    return textwrap.fill(text, width=chars_per_line)


def _looks_sans(path: str) -> bool:
    name = Path(path).stem.lower()
    return any(
        k in name
        for k in (
            "montserrat",
            "poppins",
            "barlow",
            "rubik",
            "nunito",
            "raleway",
            "oswald",
            "segoe",
            "arial",
            "calibri",
            "verdana",
            "tahoma",
            "sans",
        )
    )


def split_brand_highlight(text: str, brand_names: list[str] | None = None) -> list[tuple[str, bool]]:
    """Parte el texto en segmentos (texto, es_marca)."""
    if not text:
        return []
    names = [n.strip() for n in (brand_names or []) if n and len(n.strip()) >= 2]
    if not names:
        return [(text, False)]
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
