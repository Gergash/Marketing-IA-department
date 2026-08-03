"""Escaneo minucioso del manual de marca: paleta visual + logos embebidos + tipografía OCR.

Combina:
1) Imágenes embebidas del PDF (candidatos a logo)
2) Paleta dominante de páginas rasterizadas (Pillow)
3) Recortes de cabecera (logos compuestos / sin xref)
"""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BrandScanResult:
    """Resultado del escaneo visual del PDF de marca."""

    palette_hex: list[str] = field(default_factory=list)
    logo_filenames: list[str] = field(default_factory=list)
    logo_urls: list[str] = field(default_factory=list)
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
    max_pages: int = 8,
    dpi: int = 160,
    max_logos: int = 4,
) -> BrandScanResult:
    """Escanea el PDF: paleta + logos. Guarda archivos en dest_dir."""
    from .ocr_paddle import pdf_bytes_to_png_pages

    result = BrandScanResult()
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1) Imágenes embebidas (mejor fuente de logos reales)
    embedded = _extract_embedded_images(raw, max_images=12)
    result.embedded_images = len(embedded)
    logo_bytes: list[bytes] = []
    for img in embedded:
        if _looks_like_logo(img):
            logo_bytes.append(img)

    # 2) Raster páginas → paleta + posibles logos de cabecera
    try:
        pages = pdf_bytes_to_png_pages(raw, max_pages=max_pages, dpi=dpi)
    except Exception as exc:  # noqa: BLE001
        logger.warning("brand_scan.raster_failed", error=str(exc))
        pages = []
        result.notes.append(f"raster_failed:{exc}")

    result.pages_scanned = len(pages)
    palette: list[str] = []
    for i, png in enumerate(pages):
        palette.extend(_dominant_colors(png, top_n=6))
        if i < 3 and len(logo_bytes) < max_logos:
            header_logo = _crop_header_logo_candidate(png)
            if header_logo and _looks_like_logo(header_logo):
                logo_bytes.append(header_logo)

    result.palette_hex = _rank_palette(palette, limit=8)

    # 3) Persistir logos
    saved = 0
    for blob in logo_bytes:
        if saved >= max_logos:
            break
        if not _looks_like_logo(blob):
            continue
        fname = f"{stem}_logo_{saved + 1}.png"
        try:
            normalized = _normalize_logo_png(blob)
            (dest_dir / fname).write_bytes(normalized)
            result.logo_filenames.append(fname)
            result.logo_urls.append(url_builder(tenant_id, fname))
            saved += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("brand_scan.logo_save_failed", error=str(exc))

    # 4) Guardar swatch de paleta (referencia visual)
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
        embedded=result.embedded_images,
    )
    return result


def _extract_embedded_images(raw: bytes, *, max_images: int = 12) -> list[bytes]:
    try:
        import fitz
    except ImportError:
        return []

    out: list[bytes] = []
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
                if len(data) < 800 or w < 32 or h < 32:
                    continue
                if w * h > 8_000_000:
                    continue
                # Prefer square-ish / logo-ish over full-bleed photos
                out.append(data)
                if len(out) >= max_images:
                    return out
    finally:
        doc.close()
    return out


def _dominant_colors(png_bytes: bytes, *, top_n: int = 6) -> list[str]:
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    img = img.resize((120, 120), Image.Resampling.BILINEAR)
    # Quantize to reduce noise
    q = img.quantize(colors=24, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette() or []
    counts = Counter(q.getdata())
    ranked = counts.most_common(40)
    hexes: list[str] = []
    for idx, _count in ranked:
        if idx * 3 + 2 >= len(palette):
            continue
        r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
        if _is_near_neutral(r, g, b):
            continue
        hexes.append(f"#{r:02X}{g:02X}{b:02X}")
        if len(hexes) >= top_n:
            break
    return hexes


def _rank_palette(colors: list[str], *, limit: int = 8) -> list[str]:
    counts = Counter(c.upper() for c in colors if c)
    # Prefer saturated brand colors
    scored: list[tuple[float, str, int]] = []
    for hx, n in counts.items():
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        sat = max(r, g, b) - min(r, g, b)
        scored.append((sat * 0.5 + n * 10, hx, n))
    scored.sort(reverse=True)
    return [hx for _, hx, _ in scored[:limit]]


def _is_near_neutral(r: int, g: int, b: int) -> bool:
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 18 and (mx > 235 or mn < 25):
        return True  # near white/black
    if mx - mn < 12:
        return True  # gray
    return False


def _crop_header_logo_candidate(png_bytes: bytes) -> bytes | None:
    """Recorta zona superior buscando mancha de color compacta (logo compuesto)."""
    from PIL import Image, ImageFilter

    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    w, h = img.size
    header = img.crop((0, 0, w, max(40, int(h * 0.22))))
    # Alpha mask: pixels that aren't near-white
    px = header.load()
    hw, hh = header.size
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
    if len(xs) < 80:
        return None
    left, right = max(0, min(xs) - 8), min(hw, max(xs) + 8)
    top, bot = max(0, min(ys) - 8), min(hh, max(ys) + 8)
    bw, bh = right - left, bot - top
    if bw < 40 or bh < 20:
        return None
    if bw > hw * 0.92 and bh > hh * 0.7:
        return None  # almost full header band = probably not a logo mark
    crop = header.crop((left, top, right, bot))
    # Soft edge cleanup
    crop = crop.filter(ImageFilter.SMOOTH_MORE)
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()


def _looks_like_logo(img_bytes: bytes) -> bool:
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    except Exception:
        return False
    w, h = img.size
    if w < 40 or h < 20:
        return False
    if w > 2200 or h > 2200:
        return False
    ratio = w / max(h, 1)
    if ratio > 8 or ratio < 0.12:
        return False
    # Reject near-blank
    small = img.resize((64, 64), Image.Resampling.BILINEAR)
    colors = small.getcolors(64 * 64) or []
    if len(colors) < 3:
        return False
    return True


def _normalize_logo_png(img_bytes: bytes) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    # Cap size for overlays / prompts
    max_side = 512
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _palette_swatch_png(hexes: list[str], *, width: int = 480, height: int = 64) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    n = max(1, len(hexes))
    slot = width // n
    for i, hx in enumerate(hexes):
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        draw.rectangle([i * slot, 0, (i + 1) * slot, height], fill=(r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
