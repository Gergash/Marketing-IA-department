"""Tests: contraste tipográfico y resolución de modelos Venice video."""

from __future__ import annotations

import io

from PIL import Image

from agents.marketing_agents.text_contrast import pick_text_colors, region_luminance, text_safe_box
from agents.marketing_agents.venice_video_models import (
    resolve_venice_video_model,
)


def _solid(color: tuple[int, int, int], size=(200, 200)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_region_luminance_dark_vs_light() -> None:
    dark = _solid((10, 10, 10))
    light = _solid((240, 240, 240))
    assert region_luminance(dark, (0, 0, 200, 200)) < 40
    assert region_luminance(light, (0, 0, 200, 200)) > 200


def test_pick_text_colors_contrasts_with_background() -> None:
    dark = _solid((20, 20, 30))
    fill, _shadow, _sec = pick_text_colors(dark, text_box=(20, 100, 180, 180))
    assert fill[0] >= 200  # texto claro sobre fondo oscuro

    light = _solid((245, 245, 240))
    fill2, _, _ = pick_text_colors(light, text_box=(20, 100, 180, 180))
    assert fill2[0] <= 60  # texto oscuro sobre fondo claro


def test_text_safe_box_lower_does_not_cover_center() -> None:
    box = text_safe_box(1080, 1350, zone="lower")
    assert box[1] >= int(1350 * 0.55)


def test_resolve_venice_video_aliases() -> None:
    assert resolve_venice_video_model("seedance-2.0") == "seedance-2-0-text-to-video"
    assert (
        resolve_venice_video_model("seedance-2.5", for_image=True)
        == "seedance-2-0-image-to-video"
    )
    assert resolve_venice_video_model("kling-o3") == "kling-o3-standard-text-to-video"
    assert "minimax" in resolve_venice_video_model("minimax-h3")


def test_logo_score_prefers_mark_over_photo() -> None:
    from agents.marketing_agents.brand_scan import _logo_score

    logo = Image.new("RGBA", (160, 80), (0, 0, 0, 0))
    for x in range(20, 140):
        for y in range(15, 65):
            logo.putpixel((x, y), (180, 30, 40, 255))
    buf = io.BytesIO()
    logo.save(buf, format="PNG")
    assert _logo_score(buf.getvalue()) >= 0.35

    photo = Image.new("RGB", (128, 96))
    pixels = photo.load()
    for x in range(128):
        for y in range(96):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, (x + y * 3) % 256)
    buf2 = io.BytesIO()
    photo.save(buf2, format="PNG")
    # foto con muchos colores únicos → score bajo
    assert _logo_score(buf2.getvalue()) < _logo_score(buf.getvalue())
