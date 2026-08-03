"""Composición editorial post-generación: overlays por arquetipo de layout."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from .layout_archetypes import LayoutArchetype, hex_to_rgb
from .overlay_text import (
    build_overlay_lines,
    pick_font_pair,
    resolve_font_roles,
    split_brand_highlight,
    wrap_for_width,
)


def _load_fonts(
    seed: str,
    title_size: int,
    body_size: int,
    *,
    preferred_font_paths: list[str] | None = None,
) -> tuple:
    (title_path, ts), (body_path, bs) = pick_font_pair(
        seed, body_size, preferred_font_paths=preferred_font_paths
    )
    try:
        return (
            ImageFont.truetype(title_path, size=ts),
            ImageFont.truetype(body_path, size=bs),
            ImageFont.truetype(body_path, size=max(12, bs - 2)),
        )
    except Exception:
        default = ImageFont.load_default()
        return default, default, default


def _truetype(path: str, size: int):
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()


def apply_design_layout(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str = "instagram",
    content_format: str = "feed",
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
) -> bytes:
    """Aplica overlay editorial según arquetipo (feed) o composición centrada (story)."""
    headline_line, subline_line = build_overlay_lines(headline=headline, subline=subline)
    kwargs = {
        "font_seed": font_seed,
        "preferred_font_paths": preferred_font_paths,
        "logo_path": logo_path,
        "tagline": tagline,
        "brand_names": brand_names,
    }
    if (content_format or "").strip().lower() == "story":
        return _layout_story_centered(
            img_bytes, archetype, headline_line, subline_line, cta, **kwargs
        )
    handlers = {
        "brand_campaign_piece": _layout_brand_campaign_piece,
        "typographic_poster": _layout_typographic_poster,
        "minimal_conceptual": _layout_minimal_conceptual,
        "editorial_infographic": _layout_editorial_infographic,
        "cinematic_hero": _layout_cinematic_hero,
    }
    handler = handlers.get(archetype.id, _layout_typographic_poster)
    return handler(img_bytes, archetype, headline_line, subline_line, cta, **kwargs)


def _multiline_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    y: int,
    canvas_w: int,
    font,
    fill: tuple,
    shadow: tuple | None = None,
) -> int:
    """Dibuja texto centrado horizontalmente; devuelve la altura ocupada."""
    tw, th = _multiline_size(draw, text, font)
    x = max(24, (canvas_w - tw) // 2)
    if shadow:
        draw.multiline_text((x + 2, y + 2), text, font=font, fill=shadow, align="center")
    draw.multiline_text((x, y), text, font=font, fill=fill, align="center")
    return th


def _layout_story_centered(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
) -> bytes:
    """Historias 9:16: tipografía y CTA centrados en el eje visual (no pegados abajo/izquierda)."""
    primary = hex_to_rgb(archetype.primary_hex)
    secondary = hex_to_rgb(archetype.secondary_hex)
    accent = hex_to_rgb(archetype.accent_hex)

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size

    # Viñeta suave + banda central semitransparente para legibilidad
    band_top = int(h * 0.28)
    band_bot = int(h * 0.72)
    for i in range(h):
        if i < band_top:
            t = 1.0 - (i / max(1, band_top))
            alpha = int(110 * t)
        elif i > band_bot:
            t = (i - band_bot) / max(1, h - band_bot)
            alpha = int(130 * t)
        else:
            alpha = 90
        if alpha:
            draw.line([(0, i), (w, i)], fill=(0, 0, 0, alpha))

    # Stories son altas: tipografía un poco más grande y márgenes laterales generosos
    title_size = max(28, min(56, w // 12))
    body_size = max(18, title_size - 10)
    font_title, font_body, font_cta = _load_fonts(
        font_seed, title_size, body_size, preferred_font_paths=preferred_font_paths
    )

    margin_x = int(w * 0.12)
    text_width = w - margin_x * 2
    wrapped = wrap_for_width(headline.upper(), text_width, font_size=title_size)
    wrapped_sub = (
        wrap_for_width(subline, text_width, font_size=body_size) if subline else None
    )

    head_h = _multiline_size(draw, wrapped, font_title)[1]
    sub_h = _multiline_size(draw, wrapped_sub, font_body)[1] if wrapped_sub else 0
    gap = 18 if wrapped_sub else 0
    cta_gap = 28
    # Estimar altura CTA para centrar el bloque completo
    cta_est_h = 44 if cta else 0
    block_h = head_h + gap + sub_h + (cta_gap + cta_est_h if cta else 0)
    y = max(int(h * 0.22), (h - block_h) // 2)

    y += _draw_centered_text(
        draw,
        wrapped,
        y=y,
        canvas_w=w,
        font=font_title,
        fill=primary + (255,),
        shadow=(0, 0, 0, 140),
    )

    if wrapped_sub:
        y += gap
        # Línea de acento centrada bajo el headline
        accent_w = int(w * 0.18)
        ax0 = (w - accent_w) // 2
        draw.rectangle([(ax0, y), (ax0 + accent_w, y + 3)], fill=accent + (255,))
        y += 14
        y += _draw_centered_text(
            draw,
            wrapped_sub,
            y=y,
            canvas_w=w,
            font=font_body,
            fill=secondary + (245,),
        )

    if cta:
        y += cta_gap
        _draw_cta_pill(
            draw,
            cta,
            w,
            h,
            font_cta,
            accent=accent,
            y_offset=y,
            center=True,
        )

    return _composite(img, overlay, logo_path=logo_path)


def _layout_typographic_poster(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
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
    font_title, font_body, font_cta = _load_fonts(
        font_seed, title_size, title_size - 6, preferred_font_paths=preferred_font_paths
    )

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

    return _composite(img, overlay, logo_path=logo_path)


def _layout_minimal_conceptual(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
) -> bytes:
    """Estilo YaComercio: headline arriba, acento en línea, mucho aire."""
    primary = hex_to_rgb(archetype.primary_hex)
    accent = hex_to_rgb(archetype.accent_hex)

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size

    title_size = max(20, min(40, w // 18))
    font_title, font_body, font_cta = _load_fonts(
        font_seed, title_size, title_size - 4, preferred_font_paths=preferred_font_paths
    )

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

    return _composite(img, overlay, logo_path=logo_path)


def _layout_editorial_infographic(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
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
    font_title, font_body, font_cta = _load_fonts(
        font_seed, title_size, title_size - 4, preferred_font_paths=preferred_font_paths
    )

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

    return _composite(img, overlay, logo_path=logo_path)


def _layout_cinematic_hero(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
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
    font_title, font_body, font_cta = _load_fonts(
        font_seed, title_size, title_size - 5, preferred_font_paths=preferred_font_paths
    )

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

    return _composite(img, overlay, logo_path=logo_path)


def _layout_brand_campaign_piece(
    img_bytes: bytes,
    archetype: LayoutArchetype,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
) -> bytes:
    """
    Pieza canónica con manual de marca (nivel ChatGPT / Tres Amores):
    foto full-bleed + logo top-center + headline script + cuerpo sans con
    highlight de marca + CTA + tagline serif. Tipografía = Pillow, no el modelo.
    """
    # Texto legible: blanco / crema sobre foto oscura; accent para marca y CTA
    white = (255, 255, 255)
    cream = hex_to_rgb(archetype.secondary_hex) if archetype.secondary_hex else (245, 230, 200)
    # Si secondary es muy oscuro, forzar crema legible
    if sum(cream) < 300:
        cream = (245, 230, 200)
    accent = hex_to_rgb(archetype.accent_hex)

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size

    # Viñeta suave: más aire en el centro (producto visible)
    for i in range(h):
        if i < int(h * 0.18):
            t = 1.0 - (i / max(1, int(h * 0.18)))
            alpha = int(80 * t)
        elif i > int(h * 0.68):
            t = (i - int(h * 0.68)) / max(1, h - int(h * 0.68))
            alpha = int(120 * t)
        else:
            alpha = 20
        if alpha:
            draw.line([(0, i), (w, i)], fill=(0, 0, 0, alpha))

    inset = max(8, w // 80)
    stroke = max(2, w // 400)
    draw.rectangle(
        [(inset, inset), (w - inset - 1, h - inset - 1)],
        outline=accent + (180,),
        width=stroke,
    )

    logo_bottom = int(h * 0.035)
    if logo_path:
        logo_bottom = _paste_logo_top_center(img, logo_path, max_h=int(h * 0.12))

    roles = resolve_font_roles(
        font_seed=font_seed,
        preferred_font_paths=preferred_font_paths,
        prefer_script_display=True,
    )
    # Script grande (Great Vibes se lee mejor un poco más grande)
    title_size = max(36, min(72, w // 9))
    body_size = max(17, min(28, w // 28))
    cta_size = max(15, body_size - 1)
    tag_size = max(15, body_size - 2)

    font_display = _truetype(roles.display, title_size)
    font_body = _truetype(roles.body, body_size)
    font_cta = _truetype(roles.cta, cta_size)
    font_tag = _truetype(roles.tagline, tag_size)

    margin_x = int(w * 0.10)
    text_w = w - margin_x * 2
    # Script: menos chars por línea (más anchos)
    wrapped = wrap_for_width(headline, text_w, font_size=int(title_size * 0.75))
    wrapped_sub = wrap_for_width(subline, text_w, font_size=body_size) if subline else None

    y = max(logo_bottom + int(h * 0.025), int(h * 0.13))
    y += _draw_centered_text(
        draw,
        wrapped,
        y=y,
        canvas_w=w,
        font=font_display,
        fill=white + (255,),
        shadow=(0, 0, 0, 170),
    )

    accent_w = int(w * 0.20)
    ax0 = (w - accent_w) // 2
    y += 12
    draw.line([(ax0, y), (ax0 + accent_w, y)], fill=accent + (230,), width=2)
    y += 16

    if wrapped_sub:
        y += _draw_centered_rich_line(
            draw,
            wrapped_sub,
            y=y,
            canvas_w=w,
            font=font_body,
            fill=cream + (250,),
            accent_fill=accent + (255,),
            brand_names=brand_names,
            shadow=(0, 0, 0, 110),
        )

    if cta:
        cta_y = min(int(h * 0.80), y + int(h * 0.08))
        cta_y = max(cta_y, int(h * 0.72))
        _draw_cta_pill(
            draw,
            cta,
            w,
            h,
            font_cta,
            accent=accent,
            y_offset=cta_y,
            center=True,
            bordered=True,
            border_color=cream,
        )

    if tagline:
        tag_wrapped = wrap_for_width(tagline, int(w * 0.82), font_size=tag_size)
        _draw_centered_text(
            draw,
            tag_wrapped,
            y=int(h * 0.90),
            canvas_w=w,
            font=font_tag,
            fill=accent + (245,),
            shadow=(0, 0, 0, 100),
        )

    return _composite(img, overlay)


def _draw_centered_rich_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    y: int,
    canvas_w: int,
    font,
    fill: tuple,
    accent_fill: tuple,
    brand_names: list[str] | None,
    shadow: tuple | None = None,
) -> int:
    """Dibuja líneas centradas resaltando el nombre de marca en accent_fill."""
    lines = text.split("\n")
    total_h = 0
    line_gap = 6
    for line in lines:
        segments = split_brand_highlight(line, brand_names)
        widths = []
        for seg, _is_brand in segments:
            bbox = draw.textbbox((0, 0), seg, font=font)
            widths.append(bbox[2] - bbox[0])
        line_w = sum(widths)
        x = max(16, (canvas_w - line_w) // 2)
        line_h = 0
        for (seg, is_brand), seg_w in zip(segments, widths):
            color = accent_fill if is_brand else fill
            if shadow:
                draw.text((x + 2, y + 2 + total_h), seg, font=font, fill=shadow)
            draw.text((x, y + total_h), seg, font=font, fill=color)
            bbox = draw.textbbox((0, 0), seg, font=font)
            line_h = max(line_h, bbox[3] - bbox[1])
            x += seg_w
        total_h += line_h + line_gap
    return max(0, total_h - line_gap)


def _paste_logo_top_center(base: Image.Image, logo_path: str, *, max_h: int) -> int:
    """Pega el logo del manual arriba-centro; devuelve Y inferior del logo en el canvas."""
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except Exception:
        return int(base.height * 0.04)
    lw, lh = logo.size
    if lh <= 0 or lw <= 0:
        return int(base.height * 0.04)
    scale = min(max_h / lh, (base.width * 0.42) / lw)
    nw, nh = max(1, int(lw * scale)), max(1, int(lh * scale))
    logo = logo.resize((nw, nh), Image.Resampling.LANCZOS)
    x = (base.width - nw) // 2
    y = max(12, int(base.height * 0.035))
    base.alpha_composite(logo, (x, y))
    return y + nh


def _draw_cta_pill(
    draw: ImageDraw.ImageDraw,
    cta: str,
    w: int,
    h: int,
    font,
    *,
    accent: tuple[int, int, int],
    y_offset: int | None = None,
    center: bool = False,
    bordered: bool = False,
    border_color: tuple[int, int, int] | None = None,
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
    cta_x = (w - pill_w) // 2 if center else 20

    draw.rounded_rectangle(
        [(cta_x, cta_y), (cta_x + pill_w, cta_y + pill_h)],
        radius=10,
        fill=accent + (230,),
    )
    if bordered:
        edge = border_color or (255, 255, 255)
        draw.rounded_rectangle(
            [(cta_x, cta_y), (cta_x + pill_w, cta_y + pill_h)],
            radius=10,
            outline=edge + (220,),
            width=2,
        )

    text_draw_x = cta_x + pad_x - bbox[0]
    text_draw_y = cta_y + pad_y - bbox[1]

    draw.text((text_draw_x, text_draw_y), cta_label, font=font, fill=(255, 255, 255, 255))


def _paste_brand_logo(
    base: Image.Image,
    logo_path: str | None,
    *,
    margin: int = 36,
    max_width_ratio: float = 0.22,
) -> Image.Image:
    """Pega el logo del manual (esquina superior derecha) si existe."""
    if not logo_path:
        return base
    from pathlib import Path

    path = Path(logo_path)
    if not path.is_file():
        return base
    try:
        logo = Image.open(path).convert("RGBA")
    except Exception:
        return base
    w, h = base.size
    max_w = max(48, int(w * max_width_ratio))
    scale = min(1.0, max_w / max(logo.width, 1))
    if scale < 1.0:
        logo = logo.resize(
            (max(1, int(logo.width * scale)), max(1, int(logo.height * scale))),
            Image.Resampling.LANCZOS,
        )
    x = w - logo.width - margin
    y = margin
    canvas = base.convert("RGBA")
    canvas.alpha_composite(logo, (x, y))
    return canvas


def _composite(img: Image.Image, overlay: Image.Image, *, logo_path: str | None = None) -> bytes:
    composite = Image.alpha_composite(img, overlay)
    # Solo esquina si el layout no pegó el logo antes (p.ej. brand_campaign lo pone arriba-centro)
    composite = _paste_brand_logo(composite, logo_path)
    buf = io.BytesIO()
    composite.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
