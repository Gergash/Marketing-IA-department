"""Escaneo minucioso del manual de marca.

Detecta y persiste:
1) Logos (embebidos + recortes de zona)
2) Paleta / roles de color (primario, secundario, acento)
3) Tipografías (fuentes embebidas del PDF + pistas OCR/texto)
4) Disposiciones (dónde va el logo, densidad tipográfica → arquetipo sugerido)
"""

from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_KNOWN_FONT_ALIASES: dict[str, str] = {
    "montserrat": "Montserrat",
    "poppins": "Poppins",
    "inter": "Inter",
    "roboto": "Roboto",
    "robotoslab": "Roboto Slab",
    "raleway": "Raleway",
    "lato": "Lato",
    "opensans": "Open Sans",
    "open sans": "Open Sans",
    "playfair": "Playfair Display",
    "playfairdisplay": "Playfair Display",
    "georgia": "Georgia",
    "helvetica": "Helvetica",
    "helveticaneue": "Helvetica Neue",
    "arial": "Arial",
    "futura": "Futura",
    "gotham": "Gotham",
    "proxima": "Proxima Nova",
    "proximanova": "Proxima Nova",
    "nunito": "Nunito",
    "oswald": "Oswald",
    "bebas": "Bebas Neue",
    "bebasneue": "Bebas Neue",
    "impact": "Impact",
    "segoe": "Segoe UI",
    "segoeui": "Segoe UI",
    "calibri": "Calibri",
    "verdana": "Verdana",
    "trebuchet": "Trebuchet MS",
    "courier": "Courier",
    "times": "Times New Roman",
    "timesnewroman": "Times New Roman",
    "greatvibes": "Great Vibes",
    "barlow": "Barlow",
    "rubik": "Rubik",
    "anton": "Anton",
    "archivoblack": "Archivo Black",
    "sourcesans": "Source Sans",
    "sourcesanspro": "Source Sans",
    "dmsans": "DM Sans",
    "spacegrotesk": "Space Grotesk",
    "cabinetgrotesk": "Cabinet Grotesk",
}

_FONT_HINT_RE = re.compile(
    r"(?:fuente|tipograf[ií]a|font(?:[\s_-]?family)?|typeface|type\s*face|"
    r"lettering|caligraf[ií]a|sans[\s-]?serif|serif)\s*[:\-]?\s*"
    r"([A-Za-z][A-Za-z0-9 \-]{1,40})",
    re.IGNORECASE,
)

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


@dataclass
class BrandScanResult:
    """Resultado del escaneo visual + tipográfico + layout del PDF de marca."""

    palette_hex: list[str] = field(default_factory=list)
    color_roles: dict[str, str] = field(default_factory=dict)  # primary/secondary/accent
    logo_filenames: list[str] = field(default_factory=list)
    logo_urls: list[str] = field(default_factory=list)
    logo_placements: list[str] = field(default_factory=list)
    font_names: list[str] = field(default_factory=list)
    layout_hints: list[str] = field(default_factory=list)
    suggested_archetype: str | None = None
    pages_scanned: int = 0
    embedded_images: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def scan_brand_pdf(
    raw: bytes,
    *,
    dest_dir: Path,
    tenant_id: str,
    stem: str,
    url_builder,
    max_pages: int = 10,
    dpi: int = 160,
    max_logos: int = 5,
    text: str = "",
) -> BrandScanResult:
    """Escanea el PDF: logos, paleta, tipografías y disposiciones."""
    from .ocr_paddle import pdf_bytes_to_png_pages

    result = BrandScanResult()
    dest_dir.mkdir(parents=True, exist_ok=True)

    # --- Tipografías embebidas en el PDF ---
    pdf_fonts = _extract_pdf_font_names(raw)
    text_fonts = _fonts_from_text(text)
    result.font_names = _merge_unique(pdf_fonts + text_fonts, limit=8)
    if pdf_fonts:
        result.notes.append(f"pdf_fonts:{len(pdf_fonts)}")
    if text_fonts:
        result.notes.append(f"text_fonts:{len(text_fonts)}")

    # Hex explícitos en el texto del manual
    text_hexes = [_normalize_hex(h) for h in _HEX_RE.findall(text or "")]

    # --- Logos embebidos ---
    embedded = _extract_embedded_images(raw, max_images=28)
    result.embedded_images = len(embedded)
    candidates: list[tuple[float, bytes, str]] = []  # score, bytes, placement hint
    for img in embedded:
        score = _logo_score(img)
        if score >= 0.32:
            candidates.append((score, img, "embedded"))

    # --- Raster páginas → paleta + logos de zona + layout ---
    try:
        pages = pdf_bytes_to_png_pages(raw, max_pages=max_pages, dpi=dpi)
    except Exception as exc:  # noqa: BLE001
        logger.warning("brand_scan.raster_failed", error=str(exc))
        pages = []
        result.notes.append(f"raster_failed:{exc}")

    result.pages_scanned = len(pages)
    palette: list[str] = list(text_hexes)
    layout_votes: list[dict] = []
    placement_votes: Counter[str] = Counter()

    for i, png in enumerate(pages):
        palette.extend(_dominant_colors(png, top_n=8, keep_brand_neutrals=True))
        palette.extend(_swatch_band_colors(png, top_n=6))
        layout = _analyze_page_layout(png)
        layout_votes.append(layout)
        for place, crop in _crop_logo_regions_labeled(png):
            score = _logo_score(crop)
            if score >= 0.32:
                candidates.append((score + 0.05, crop, place))  # bonus zona tipica
                placement_votes[place] += 1
        # También colores del crop de logo
        for place, crop in _crop_logo_regions_labeled(png)[:2]:
            palette.extend(_dominant_colors(crop, top_n=3, keep_brand_neutrals=False))

    result.palette_hex = _rank_palette(palette, limit=10)
    result.color_roles = _assign_color_roles(result.palette_hex)

    # Disposiciones agregadas
    result.layout_hints, result.suggested_archetype = _summarize_layouts(
        layout_votes, placement_votes, font_names=result.font_names
    )
    result.logo_placements = [p for p, _ in placement_votes.most_common(4)]

    # --- Persistir logos ---
    candidates.sort(key=lambda t: t[0], reverse=True)
    saved = 0
    seen_sig: set[str] = set()
    for score, blob, place in candidates:
        if saved >= max_logos:
            break
        sig = _image_signature(blob)
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        fname = f"{stem}_logo_{saved + 1}.png"
        try:
            normalized = _normalize_logo_png(blob)
            (dest_dir / fname).write_bytes(normalized)
            result.logo_filenames.append(fname)
            result.logo_urls.append(url_builder(tenant_id, fname))
            result.notes.append(f"logo_score:{saved + 1}={score:.2f}:{place}")
            if place and place != "embedded" and place not in result.logo_placements:
                result.logo_placements.append(place)
            saved += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("brand_scan.logo_save_failed", error=str(exc))

    # Swatch de paleta
    if result.palette_hex:
        try:
            swatch = _palette_swatch_png(result.palette_hex)
            swatch_name = f"{stem}_palette.png"
            (dest_dir / swatch_name).write_bytes(swatch)
            result.notes.append(f"palette_swatch:{swatch_name}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("brand_scan.swatch_failed", error=str(exc))

    logger.info(
        "brand_scan.done",
        pages=result.pages_scanned,
        palette=result.palette_hex[:5],
        logos=len(result.logo_urls),
        fonts=result.font_names[:4],
        archetype=result.suggested_archetype,
        placements=result.logo_placements[:3],
        embedded=result.embedded_images,
    )
    return result


# ---------------------------------------------------------------------------
# Tipografías
# ---------------------------------------------------------------------------


def _extract_pdf_font_names(raw: bytes) -> list[str]:
    try:
        import fitz
    except ImportError:
        return []

    names: list[str] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        for page in doc:
            try:
                fonts = page.get_fonts(full=True)
            except Exception:
                fonts = []
            for item in fonts:
                # (xref, ext, type, basefont, name, encoding, ...)
                base = ""
                if len(item) >= 4:
                    base = str(item[3] or "")
                if not base and len(item) > 4:
                    base = str(item[4] or "")
                cleaned = _clean_pdf_font_name(base)
                mapped = _map_known_font(cleaned) or cleaned
                if mapped and mapped not in names:
                    names.append(mapped)
    finally:
        doc.close()
    return names[:10]


def _clean_pdf_font_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    # Quitar subset prefix ABCDEF+FontName
    if "+" in raw:
        raw = raw.split("+", 1)[-1]
    raw = re.sub(r"[,:].*$", "", raw)
    raw = re.sub(r"(MT|PS|Regular|Bold|Italic|Light|Medium|Black|Heavy)$", "", raw, flags=re.I)
    raw = re.sub(r"[-_]+", " ", raw).strip()
    if len(raw) < 3:
        return ""
    # Descartar fuentes genéricas del sistema PDF
    lower = raw.lower().replace(" ", "")
    if lower in {"helv", "heit", "cour", "times", "symbol", "zapfdingbats", "cidfont"}:
        return ""
    return raw.title() if raw.islower() else raw


def _map_known_font(name: str) -> str | None:
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if not key:
        return None
    for alias, pretty in _KNOWN_FONT_ALIASES.items():
        alias_key = re.sub(r"[^a-z0-9]", "", alias)
        if alias_key and (alias_key in key or key in alias_key):
            return pretty
    return None


def _fonts_from_text(text: str) -> list[str]:
    if not (text or "").strip():
        return []
    found: list[str] = []
    lower = text.lower()
    for m in _FONT_HINT_RE.finditer(text):
        name = m.group(1).strip(" .,;:-")
        if len(name) < 3:
            continue
        if name.lower() in {"logo", "logotipo", "isotipo", "sans", "serif", "bold"}:
            continue
        mapped = _map_known_font(name) or name.title()
        if mapped not in found:
            found.append(mapped)
    for alias, pretty in _KNOWN_FONT_ALIASES.items():
        if alias in lower and pretty not in found:
            found.append(pretty)
    return found[:8]


# ---------------------------------------------------------------------------
# Layout / disposiciones
# ---------------------------------------------------------------------------


def _analyze_page_layout(png_bytes: bytes) -> dict:
    """Heurística 3×3: densidades de tinta → zonas de logo/texto."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    except Exception:
        return {}
    w, h = img.size
    small = img.resize((90, 90), Image.Resampling.BILINEAR)
    px = small.load()
    cell = 30  # 3x3 on 90px
    densities: list[list[float]] = []
    for row in range(3):
        row_d: list[float] = []
        for col in range(3):
            ink = 0
            total = 0
            for y in range(row * cell, (row + 1) * cell):
                for x in range(col * cell, (col + 1) * cell):
                    r, g, b = px[x, y]
                    total += 1
                    if not (_is_near_neutral(r, g, b) and max(r, g, b) > 220):
                        ink += 1
            row_d.append(ink / max(total, 1))
        densities.append(row_d)

    top = densities[0]
    mid = densities[1]
    bot = densities[2]
    top_avg = sum(top) / 3
    mid_avg = sum(mid) / 3
    bot_avg = sum(bot) / 3
    center = densities[1][1]

    logo_zone = "top-center"
    if top[0] >= top[1] and top[0] >= top[2] and top[0] > 0.08:
        logo_zone = "top-left"
    elif top[2] >= top[1] and top[2] >= top[0] and top[2] > 0.08:
        logo_zone = "top-right"
    elif top[1] > 0.08:
        logo_zone = "top-center"

    return {
        "logo_zone": logo_zone,
        "top_density": round(top_avg, 3),
        "mid_density": round(mid_avg, 3),
        "bot_density": round(bot_avg, 3),
        "center_density": round(center, 3),
        "aspect": round(w / max(h, 1), 3),
    }


def _summarize_layouts(
    layouts: list[dict],
    placement_votes: Counter[str],
    *,
    font_names: list[str],
) -> tuple[list[str], str | None]:
    if not layouts and not placement_votes:
        hints = []
        if font_names:
            hints.append(f"tipografías: {', '.join(font_names[:4])}")
        return hints, "brand_campaign_piece" if font_names else None

    zones = Counter(L.get("logo_zone") for L in layouts if L.get("logo_zone"))
    for p, n in placement_votes.items():
        zones[p] += n

    top_d = [L["top_density"] for L in layouts if "top_density" in L]
    bot_d = [L["bot_density"] for L in layouts if "bot_density" in L]
    mid_d = [L["mid_density"] for L in layouts if "mid_density" in L]
    center_d = [L["center_density"] for L in layouts if "center_density" in L]

    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    at, ab, am, ac = avg(top_d), avg(bot_d), avg(mid_d), avg(center_d)

    hints: list[str] = []
    dominant_zone = zones.most_common(1)[0][0] if zones else "top-center"
    hints.append(f"logo_zone:{dominant_zone}")

    if ab > at + 0.08 and ab > 0.18:
        hints.append("texto_pesado_inferior")
    if at < 0.12 and ac < 0.15 and ab < 0.2:
        hints.append("mucho_aire_minimal")
    if am > 0.22 and abs(am - ab) < 0.1:
        hints.append("bloques_editoriales_medios")
    if ac > 0.25 and at < ab:
        hints.append("hero_central_producto")
    if dominant_zone == "top-center":
        hints.append("logo_centrado_superior")
    if font_names:
        hints.append(f"tipografías: {', '.join(font_names[:4])}")

    # Mapear a arquetipos del producto
    archetype = "brand_campaign_piece"
    if "mucho_aire_minimal" in hints:
        archetype = "minimal_conceptual"
    elif "bloques_editoriales_medios" in hints:
        archetype = "editorial_infographic"
    elif "hero_central_producto" in hints and "texto_pesado_inferior" in hints:
        archetype = "cinematic_hero"
    elif "texto_pesado_inferior" in hints and dominant_zone in {"top-left", "top-right"}:
        archetype = "typographic_poster"
    elif dominant_zone == "top-center":
        archetype = "brand_campaign_piece"

    return hints[:8], archetype


# ---------------------------------------------------------------------------
# Logos / crops
# ---------------------------------------------------------------------------


def _extract_embedded_images(raw: bytes, *, max_images: int = 28) -> list[bytes]:
    try:
        import fitz
    except ImportError:
        return []

    scored: list[tuple[float, bytes]] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        seen: set[int] = set()
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    meta = doc.extract_image(xref)
                except Exception:
                    continue
                data = meta.get("image") or b""
                w = int(meta.get("width") or 0)
                h = int(meta.get("height") or 0)
                if len(data) < 600 or w < 24 or h < 24:
                    continue
                if w * h > 8_000_000:
                    continue
                ratio = w / max(h, 1)
                compactness = 1.0 / (1.0 + abs(ratio - 1.2) * 0.35)
                size_bonus = 1.0 if 48 <= max(w, h) <= 900 else 0.55
                scored.append((compactness * size_bonus, data))
    finally:
        doc.close()
    scored.sort(key=lambda t: t[0], reverse=True)
    return [blob for _, blob in scored[:max_images]]


def _crop_logo_regions_labeled(png_bytes: bytes) -> list[tuple[str, bytes]]:
    """Recorta cabecera/esquinas/pie con etiqueta de placement."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception:
        return []
    w, h = img.size
    regions = [
        ("top-full", (0, 0, w, max(40, int(h * 0.22)))),
        ("top-left", (0, 0, max(40, int(w * 0.42)), max(40, int(h * 0.20)))),
        ("top-right", (max(0, w - int(w * 0.42)), 0, w, max(40, int(h * 0.20)))),
        ("top-center", (max(0, int(w * 0.25)), 0, min(w, int(w * 0.75)), max(40, int(h * 0.18)))),
        ("bottom-center", (max(0, int(w * 0.2)), max(0, int(h * 0.82)), min(w, int(w * 0.8)), h)),
    ]
    out: list[tuple[str, bytes]] = []
    for label, box in regions:
        crop = _extract_ink_bbox(img.crop(box))
        if crop:
            out.append((label if label != "top-full" else "top-center", crop))
    return out


def _crop_logo_regions(png_bytes: bytes) -> list[bytes]:
    return [c for _, c in _crop_logo_regions_labeled(png_bytes)]


def _crop_header_logo_candidate(png_bytes: bytes) -> bytes | None:
    crops = _crop_logo_regions(png_bytes)
    return crops[0] if crops else None


def _extract_ink_bbox(region) -> bytes | None:
    from PIL import ImageFilter

    px = region.load()
    hw, hh = region.size
    ys, xs = [], []
    for y in range(hh):
        for x in range(hw):
            r, g, b, a = px[x, y]
            if a < 30:
                continue
            if _is_near_neutral(r, g, b) and max(r, g, b) > 220:
                continue
            xs.append(x)
            ys.append(y)
    if len(xs) < 50:
        return None
    left, right = max(0, min(xs) - 8), min(hw, max(xs) + 8)
    top, bot = max(0, min(ys) - 8), min(hh, max(ys) + 8)
    bw, bh = right - left, bot - top
    if bw < 28 or bh < 14:
        return None
    if bw > hw * 0.95 and bh > hh * 0.78:
        return None
    crop = region.crop((left, top, right, bot))
    crop = crop.filter(ImageFilter.SMOOTH_MORE)
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()


def _looks_like_logo(img_bytes: bytes) -> bool:
    return _logo_score(img_bytes) >= 0.35


def _logo_score(img_bytes: bytes) -> float:
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    except Exception:
        return 0.0
    w, h = img.size
    if w < 32 or h < 16:
        return 0.0
    if w > 2400 or h > 2400:
        return 0.0
    ratio = w / max(h, 1)
    if ratio > 10 or ratio < 0.1:
        return 0.0

    small = img.resize((64, 64), Image.Resampling.BILINEAR)
    pixels = list(small.getdata())
    opaque = [(r, g, b, a) for r, g, b, a in pixels if a > 40]
    if len(opaque) < 40:
        return 0.0

    coverage = len(opaque) / max(len(pixels), 1)
    if coverage < 0.04 or coverage > 0.98:
        return 0.05

    unique = {(r // 16, g // 16, b // 16) for r, g, b, _ in opaque}
    n_unique = len(unique)
    if n_unique < 1:
        return 0.05
    if n_unique == 1:
        color_score = 0.85 if coverage < 0.92 else 0.25
    elif 2 <= n_unique <= 28:
        color_score = 1.0
    elif n_unique <= 48:
        color_score = 0.45
    else:
        color_score = 0.15

    alpha_vals = [a for *_, a in pixels]
    has_alpha = any(a < 200 for a in alpha_vals) and any(a > 200 for a in alpha_vals)
    alpha_bonus = 0.2 if has_alpha else 0.0
    aspect_score = 1.0 if 0.35 <= ratio <= 4.5 else 0.45
    size_score = 1.0 if 40 <= max(w, h) <= 1200 else 0.5

    score = (
        0.35 * color_score
        + 0.25 * aspect_score
        + 0.20 * size_score
        + 0.10 * min(1.0, coverage * 2)
        + alpha_bonus
    )
    return max(0.0, min(1.0, score))


def _image_signature(img_bytes: bytes) -> str:
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((16, 16), Image.Resampling.BILINEAR)
    except Exception:
        return str(hash(img_bytes[:64]))
    return "".join(f"{(r >> 5)}{(g >> 5)}{(b >> 5)}" for r, g, b in img.getdata())


def _normalize_logo_png(img_bytes: bytes) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    max_side = 512
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Colores
# ---------------------------------------------------------------------------


def _normalize_hex(h: str) -> str:
    h = (h or "").strip().upper()
    if re.fullmatch(r"#[0-9A-F]{3}", h):
        return "#" + "".join(ch * 2 for ch in h[1:])
    return h


def _dominant_colors(
    png_bytes: bytes,
    *,
    top_n: int = 6,
    keep_brand_neutrals: bool = False,
) -> list[str]:
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    except Exception:
        return []
    img = img.resize((140, 140), Image.Resampling.BILINEAR)
    q = img.quantize(colors=28, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette() or []
    counts = Counter(q.getdata())
    hexes: list[str] = []
    for idx, count in counts.most_common(50):
        if idx * 3 + 2 >= len(palette):
            continue
        r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
        if _is_near_neutral(r, g, b):
            # Conservar negro/blanco de marca si son muy frecuentes (páginas de paleta)
            if keep_brand_neutrals and count >= 80 and (max(r, g, b) < 40 or min(r, g, b) > 240):
                hexes.append(f"#{r:02X}{g:02X}{b:02X}")
            continue
        hexes.append(f"#{r:02X}{g:02X}{b:02X}")
        if len(hexes) >= top_n:
            break
    return hexes


def _swatch_band_colors(png_bytes: bytes, *, top_n: int = 6) -> list[str]:
    """Detecta bandas horizontales de color sólido (páginas de paleta del brand book)."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    except Exception:
        return []
    w, h = img.size
    # Muestrear filas a 1/3 y 2/3 de alto (swatches suelen ir ahí)
    colors: list[str] = []
    for y_frac in (0.35, 0.55, 0.72):
        y = min(h - 1, int(h * y_frac))
        row = [img.getpixel((x, y)) for x in range(0, w, max(1, w // 48))]
        # Agrupar por color cuantizado
        buckets: Counter[tuple[int, int, int]] = Counter()
        for r, g, b in row:
            buckets[((r // 24) * 24, (g // 24) * 24, (b // 24) * 24)] += 1
        for (r, g, b), n in buckets.most_common(4):
            if n < 3:
                continue
            if _is_near_neutral(r, g, b) and not (max(r, g, b) < 35 or min(r, g, b) > 245):
                continue
            colors.append(f"#{r:02X}{g:02X}{b:02X}")
    return _rank_palette(colors, limit=top_n)


def _rank_palette(colors: list[str], *, limit: int = 8) -> list[str]:
    counts = Counter(_normalize_hex(c) for c in colors if c)
    scored: list[tuple[float, str]] = []
    for hx, n in counts.items():
        if not hx.startswith("#") or len(hx) != 7:
            continue
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        sat = max(r, g, b) - min(r, g, b)
        # Preferir saturados; negros/blancos de marca pesan menos pero no cero
        scored.append((sat * 0.55 + n * 12, hx))
    scored.sort(reverse=True)
    return [hx for _, hx in scored[:limit]]


def _assign_color_roles(palette: list[str]) -> dict[str, str]:
    if not palette:
        return {}
    roles = {"primary": palette[0]}
    if len(palette) > 1:
        roles["accent"] = palette[1]
    if len(palette) > 2:
        roles["secondary"] = palette[2]
    elif len(palette) == 1:
        roles["accent"] = palette[0]
        roles["secondary"] = "#FFFFFF" if palette[0].upper() not in {"#FFFFFF", "#FFF"} else "#111111"
    return roles


def _is_near_neutral(r: int, g: int, b: int) -> bool:
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 18 and (mx > 235 or mn < 25):
        return True
    if mx - mn < 12:
        return True
    return False


def _palette_swatch_png(hexes: list[str], *, width: int = 480, height: int = 64) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    n = max(1, len(hexes))
    slot = width // n
    for i, hx in enumerate(hexes):
        hx = _normalize_hex(hx)
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        draw.rectangle([i * slot, 0, (i + 1) * slot, height], fill=(r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _merge_unique(items: list[str], *, limit: int = 8) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out
