"""Contraste tipográfico: color de texto que destaque del fondo y no opaque el diseño."""

from __future__ import annotations

from PIL import Image


def region_luminance(img: Image.Image, box: tuple[int, int, int, int]) -> float:
    """Luminancia media (0–255) de una región; box = (left, top, right, bottom)."""
    left, top, right, bot = box
    w, h = img.size
    left = max(0, min(w - 1, left))
    right = max(left + 1, min(w, right))
    top = max(0, min(h - 1, top))
    bot = max(top + 1, min(h, bot))
    crop = img.convert("RGB").crop((left, top, right, bot))
    small = crop.resize((24, 24), Image.Resampling.BILINEAR)
    pixels = list(small.getdata())
    if not pixels:
        return 128.0
    return sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels) / len(pixels)


def pick_text_colors(
    img: Image.Image,
    *,
    text_box: tuple[int, int, int, int],
    brand_primary: tuple[int, int, int] | None = None,
    brand_secondary: tuple[int, int, int] | None = None,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Elige fill, shadow y secondary fill con contraste frente al fondo.

    Returns:
        (fill_rgba, shadow_rgba, secondary_rgba)
    """
    lum = region_luminance(img, text_box)
    # Fondo oscuro → texto claro; fondo claro → texto oscuro
    if lum < 140:
        base = (255, 255, 255)
        shadow = (0, 0, 0, 180)
        secondary = (245, 235, 220) if not brand_secondary or _luma(brand_secondary) < 160 else brand_secondary
    else:
        base = (17, 17, 17)
        shadow = (255, 255, 255, 160)
        secondary = (40, 40, 40) if not brand_secondary or _luma(brand_secondary) > 180 else brand_secondary

    # Si el color de marca tiene buen contraste con el fondo, usarlo como fill
    fill_rgb = base
    if brand_primary and _contrast_ok(brand_primary, lum):
        fill_rgb = brand_primary
    elif brand_secondary and _contrast_ok(brand_secondary, lum):
        fill_rgb = brand_secondary

    return fill_rgb + (255,), shadow, secondary + (250,)


def text_safe_box(w: int, h: int, *, zone: str = "lower") -> tuple[int, int, int, int]:
    """Zona de texto que no tapa el centro del producto (máx ~28% de altura)."""
    margin_x = int(w * 0.08)
    if zone == "upper":
        return (margin_x, int(h * 0.04), w - margin_x, int(h * 0.28))
    if zone == "center":
        return (margin_x, int(h * 0.38), w - margin_x, int(h * 0.62))
    # lower — default: no invade el hero del producto
    return (margin_x, int(h * 0.62), w - margin_x, int(h * 0.92))


def _luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def _contrast_ok(rgb: tuple[int, int, int], bg_lum: float) -> bool:
    """Heurística simple: diferencia de luminancia ≥ 90."""
    return abs(_luma(rgb) - bg_lum) >= 90
