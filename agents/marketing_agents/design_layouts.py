"""Composición editorial post-generación: overlays por arquetipo de layout."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from .layout_archetypes import LayoutArchetype, hex_to_rgb
from .overlay_text import build_overlay_lines, pick_font_pair, wrap_for_width


def _load_fonts(seed: str, title_size: int, body_size: int) -> tuple:
    (title_path, ts), (body_path, bs) = pick_font_pair(seed, body_size)
    try:
        return (
            ImageFont.truetype(title_path, size=ts),
            ImageFont.truetype(body_path, size=bs),
            ImageFont.truetype(body_path, size=max(12, bs - 2)),
        )
    except Exception:
        default = ImageFont.load_default()
        return default, default, default


def apply_design_layout(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str = "instagram",
) -> bytes:
    """Aplica overlay editorial según arquetipo."""
    headline_line, subline_line = build_overlay_lines(headline=headline, subline=subline)
    handlers = {
        "typographic_poster": _layout_typographic_poster,
        "minimal_conceptual": _layout_minimal_conceptual,
        "editorial_infographic": _layout_editorial_infographic,
        "cinematic_hero": _layout_cinematic_hero,
    }
    handler = handlers.get(archetype.id, _layout_typographic_poster)
    return handler(img_bytes, archetype, headline_line, subline_line, cta, font_seed=font_seed)


def _layout_typographic_poster(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
) -> bytes:
    """Estilo Mattelsa/RADAR: headline grande en tercio inferior, alto contraste."""
    primary = hex_to_rgb(archetype.primary_hex)
    secondary = hex_to_rgb(archetype.secondary_hex)

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    bar_h = int(h * 0.42)

    for i in range(bar_h):
        alpha = int(200 * (i / bar_h))
        draw.line([(0, h - bar_h + i), (w, h - bar_h + i)], fill=(0, 0, 0, alpha))

    title_size = max(22, min(48, w // 16))
    font_title, font_body, font_cta = _load_fonts(font_seed, title_size, title_size - 6)

    y = h - bar_h + int(bar_h * 0.12)
    wrapped = wrap_for_width(headline.upper(), w - 48, font_size=title_size)
    for dx, dy in ((2, 2),):
        draw.text((24 + dx, y + dy), wrapped, font=font_title, fill=(0, 0, 0, 120))
    draw.text((24, y), wrapped, font=font_title, fill=primary + (255,))

    y += title_size * (wrapped.count("\n") + 1) + 10
    if subline:
        wrapped_sub = wrap_for_width(subline, w - 48, font_size=title_size - 6)
        draw.text((24, y), wrapped_sub, font=font_body, fill=secondary + (240,))

    if cta:
        _draw_cta_pill(draw, cta, w, h, font_cta, accent=primary)

    return _composite(img, overlay)


def _layout_minimal_conceptual(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
) -> bytes:
    """Estilo YaComercio: headline arriba, acento en línea, mucho aire."""
    primary = hex_to_rgb(archetype.primary_hex)
    accent = hex_to_rgb(archetype.accent_hex)

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size

    title_size = max(20, min(40, w // 18))
    font_title, font_body, font_cta = _load_fonts(font_seed, title_size, title_size - 4)

    y = int(h * 0.06)
    wrapped = wrap_for_width(headline, w - 56, font_size=title_size)
    draw.text((28, y), wrapped, font=font_title, fill=primary + (255,))
    y += title_size * (wrapped.count("\n") + 1) + 8
    draw.rectangle([(28, y), (28 + int(w * 0.15), y + 3)], fill=accent + (255,))

    if subline:
        y += 16
        wrapped_sub = wrap_for_width(subline, w - 56, font_size=title_size - 4)
        draw.text((28, y), wrapped_sub, font=font_body, fill=accent + (255,))

    if cta:
        _draw_cta_pill(draw, cta, w, h, font_cta, accent=accent, y_offset=int(h * 0.88))

    return _composite(img, overlay)


def _layout_editorial_infographic(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
) -> bytes:
    """Estilo PowerUps/RADAR infográfico: barra inferior + acento lime."""
    accent = hex_to_rgb(archetype.accent_hex)
    white = (255, 255, 255)

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    bar_h = int(h * 0.32)
    draw.rectangle([(0, h - bar_h), (w, h)], fill=(10, 10, 20, 210))

    title_size = max(18, min(36, w // 20))
    font_title, font_body, font_cta = _load_fonts(font_seed, title_size, title_size - 4)

    y = h - bar_h + 20
    wrapped = wrap_for_width(headline, w - 60, font_size=title_size)
    bbox_head = draw.multiline_textbbox((36, y), wrapped, font=font_title)
    head_h = bbox_head[3] - bbox_head[1]
    draw.rectangle([(20, y), (26, y + max(40, head_h))], fill=accent + (255,))
    draw.text((36, y), wrapped, font=font_title, fill=white + (255,))
    y += head_h + 12

    if subline:
        wrapped_sub = wrap_for_width(subline, w - 60, font_size=title_size - 4)
        bbox_sub = draw.multiline_textbbox((36, y), wrapped_sub, font=font_body)
        sub_h = bbox_sub[3] - bbox_sub[1]
        draw.rectangle([(20, y), (26, y + max(28, sub_h))], fill=accent + (180,))
        draw.text((36, y), wrapped_sub, font=font_body, fill=(220, 220, 230, 240))

    if cta:
        _draw_cta_pill(draw, cta, w, h, font_cta, accent=accent)

    return _composite(img, overlay)


def _layout_cinematic_hero(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
) -> bytes:
    """Estilo RADAR cinematográfico: gradiente inferior + texto en tercio bajo."""
    accent = hex_to_rgb(archetype.accent_hex)
    white = (255, 255, 255)

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    grad_h = int(h * 0.38)
    for i in range(grad_h):
        alpha = int(220 * (i / grad_h))
        draw.line([(0, h - grad_h + i), (w, h - grad_h + i)], fill=(0, 0, 0, alpha))

    title_size = max(20, min(42, w // 17))
    font_title, font_body, font_cta = _load_fonts(font_seed, title_size, title_size - 5)

    y = h - grad_h + int(grad_h * 0.15)
    wrapped = wrap_for_width(headline, w - 48, font_size=title_size)
    lines = wrapped.split("\n")
    for i, line in enumerate(lines):
        color = accent + (255,) if i == len(lines) - 1 and len(lines) > 1 else white + (255,)
        draw.text((24, y + i * (title_size + 4)), line, font=font_title, fill=color)

    y += title_size * len(lines) + 8
    if subline:
        wrapped_sub = wrap_for_width(subline, w - 48, font_size=title_size - 5)
        draw.text((24, y), wrapped_sub, font=font_body, fill=(230, 230, 240, 230))

    if cta:
        _draw_cta_pill(draw, cta, w, h, font_cta, accent=accent)

    return _composite(img, overlay)


def _draw_cta_pill(
    draw: ImageDraw.ImageDraw,
    cta: str,
    w: int,
    h: int,
    font,
    *,
    accent: tuple[int, int, int],
    y_offset: int | None = None,
) -> None:
    cta_label = f" {cta[:45]} "
    bbox = draw.textbbox((0, 0), cta_label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    pad_x = 16
    pad_y = 10
    
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2
    
    cta_y = y_offset if y_offset is not None else h - pill_h - 20
    cta_x = 20
    
    draw.rounded_rectangle(
        [(cta_x, cta_y), (cta_x + pill_w, cta_y + pill_h)],
        radius=8,
        fill=accent + (230,),
    )
    
    text_draw_x = cta_x + pad_x - bbox[0]
    text_draw_y = cta_y + pad_y - bbox[1]
    
    draw.text((text_draw_x, text_draw_y), cta_label, font=font, fill=(255, 255, 255, 255))


def _composite(img: Image.Image, overlay: Image.Image) -> bytes:
    composite = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    composite.save(buf, format="PNG")
    return buf.getvalue()
