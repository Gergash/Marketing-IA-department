"""Tests: escaneo visual del manual (paleta + logos) y fusión con cues de texto."""

from __future__ import annotations

import io

from PIL import Image

from agents.marketing_agents.brand_scan import (
    BrandScanResult,
    _dominant_colors,
    _looks_like_logo,
    _rank_palette,
)
from agents.marketing_agents.brand_visual import (
    brand_priority_prompt_block,
    merge_scanned_assets,
    parse_brand_visual_cues,
    resolve_brand_cues,
)


def _png(color: tuple[int, int, int], size: tuple[int, int] = (80, 80)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_dominant_colors_skips_near_white() -> None:
    # Mostly teal with white border noise in a solid image → teal
    png = _png((15, 118, 110), (100, 100))
    hexes = _dominant_colors(png, top_n=3)
    assert hexes
    assert any(h.startswith("#0") or h.startswith("#1") for h in hexes)


def test_rank_palette_prefers_saturated() -> None:
    ranked = _rank_palette(
        ["#F5F5F5", "#0F766E", "#0F766E", "#111111", "#F97316"],
        limit=3,
    )
    assert "#0F766E" in ranked
    assert ranked[0] != "#F5F5F5"


def test_looks_like_logo_rejects_tiny_and_blank() -> None:
    tiny = _png((200, 50, 50), (10, 10))
    assert _looks_like_logo(tiny) is False
    blank = _png((255, 255, 255), (100, 100))
    # nearly single-color after resize → reject
    assert _looks_like_logo(blank) is False
    logoish = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
    for x in range(20, 100):
        for y in range(10, 50):
            logoish.putpixel((x, y), (200, 40, 40, 255))
    buf = io.BytesIO()
    logoish.save(buf, format="PNG")
    assert _looks_like_logo(buf.getvalue()) is True


def test_merge_scanned_assets_overrides_empty_text_palette() -> None:
    cues = parse_brand_visual_cues("Manual sin hexes pero con tipografía Montserrat premium.")
    merged = merge_scanned_assets(
        cues,
        {
            "palette_hex": ["#0033A0", "#C8102E"],
            "logo_urls": ["http://localhost/logo.png"],
            "logo_paths": ["/tmp/logo.png"],
        },
    )
    assert merged.primary_hex == "#0033A0"
    assert merged.accent_hex == "#C8102E"
    assert merged.logo_paths == ["/tmp/logo.png"]
    assert merged.has_signal


def test_resolve_brand_cues_pantone_and_logo_mention() -> None:
    text = "Logotipo oficial. Pantone 186 C. Tipografía: Helvetica. Estilo corporativo."
    cues = resolve_brand_cues(text)
    assert cues.logo_mentions
    assert cues.primary_hex == "#C8102E"
    block = brand_priority_prompt_block(cues, text)
    assert "logo" in block.lower()
    assert "#C8102E" in block


def test_brand_scan_result_to_dict() -> None:
    r = BrandScanResult(palette_hex=["#ABC"], logo_urls=["u"], pages_scanned=2)
    d = r.to_dict()
    assert d["palette_hex"] == ["#ABC"]
    assert d["pages_scanned"] == 2
