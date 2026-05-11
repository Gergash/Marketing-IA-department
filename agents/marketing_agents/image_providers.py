from __future__ import annotations

import base64
import io
import textwrap
import uuid
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "images"
_SD_WIDTH = 768
_SD_HEIGHT = 512
_SD_STEPS = 20
_DALLE_SIZE = "1792x1024"


def generate_image(
    prompt: str,
    *,
    overlay_text: str | None = None,
    overlay_cta: str | None = None,
) -> str:
    """Return an image URL for the given prompt, with optional text overlay."""
    from gateway.app.core.settings import get_settings
    s = get_settings()

    if s.image_provider == "stable_diffusion":
        return _stable_diffusion(
            prompt,
            s.stable_diffusion_url,
            checkpoint=(s.stable_diffusion_checkpoint or "").strip() or None,
            overlay_text=overlay_text,
            overlay_cta=overlay_cta,
        )
    if s.image_provider == "openai" and s.openai_api_key:
        return _dalle(prompt, s.openai_api_key)
    if s.image_provider == "canva":
        return _canva(prompt, s)
    return _placeholder(prompt)


def _stable_diffusion(
    prompt: str,
    sd_url: str,
    *,
    checkpoint: str | None,
    overlay_text: str | None = None,
    overlay_cta: str | None = None,
) -> str:
    """
    Calls Automatic1111 / Forge WebUI REST API.
    Saves image to static/images/ and returns local URL.
    If overlay_text is provided, Pillow composites the marketing copy and CTA
    on top of the generated background — SD handles the scene, Pillow the text.
    """
    import httpx

    payload: dict = {
        "prompt": prompt[:500],
        "negative_prompt": "blurry, low quality, watermark, signature, deformed, ugly",
        "width": _SD_WIDTH,
        "height": _SD_HEIGHT,
        "steps": _SD_STEPS,
        "cfg_scale": 7,
        "sampler_name": "Euler a",
        "n_iter": 1,
        "batch_size": 1,
    }
    if checkpoint:
        payload["override_settings"] = {"sd_model_checkpoint": checkpoint}

    try:
        resp = httpx.post(sd_url, json=payload, timeout=300)
        resp.raise_for_status()
        images = resp.json().get("images", [])
        if not images:
            logger.warning("image.sd_empty_response")
            return _placeholder(prompt)

        raw = base64.b64decode(images[0])

        if overlay_text:
            raw = _add_text_overlay(raw, overlay_text, overlay_cta)

        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        (_STATIC_DIR / filename).write_bytes(raw)
        url = f"http://localhost:8000/static/images/{filename}"
        logger.info("image.sd_generated", url=url)
        return url
    except Exception as exc:
        logger.error("image.sd_error", error=str(exc))
        return _placeholder(prompt)


def _add_text_overlay(img_bytes: bytes, copy_text: str, cta: str | None) -> bytes:
    """Composites marketing copy and CTA over the SD-generated background."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    w, h = img.size
    bar_h = h // 3

    # Semi-transparent dark gradient bar at the bottom
    draw.rectangle([(0, h - bar_h), (w, h)], fill=(10, 10, 20, 185))

    # Try system font; fall back to PIL default
    try:
        font_copy = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size=17)
        font_cta = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size=15)
    except Exception:
        font_copy = ImageFont.load_default()
        font_cta = font_copy

    # Wrap and draw copy text
    wrapped = textwrap.fill(copy_text[:220], width=62)
    draw.text((20, h - bar_h + 14), wrapped, font=font_copy, fill=(255, 255, 255, 245))

    # Draw CTA pill
    if cta:
        cta_label = f"  {cta[:55]}  "
        cta_y = h - 36
        # Measure text width
        bbox = draw.textbbox((0, 0), cta_label, font=font_cta)
        cta_w = bbox[2] - bbox[0] + 4
        draw.rounded_rectangle(
            [(16, cta_y - 4), (16 + cta_w, cta_y + 20)],
            radius=6,
            fill=(255, 130, 0, 220),
        )
        draw.text((18, cta_y), cta_label, font=font_cta, fill=(255, 255, 255, 255))

    composite = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    composite.save(buf, format="PNG")
    return buf.getvalue()


def _dalle(prompt: str, api_key: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt[:4000],
            size=_DALLE_SIZE,
            quality="standard",
            n=1,
        )
        url = resp.data[0].url
        logger.info("image.dalle_generated", url=url[:80] if url else "")
        return url or _placeholder(prompt)
    except Exception as exc:
        logger.error("image.dalle_error", error=str(exc))
        return _placeholder(prompt)


def _canva(prompt: str, settings) -> str:
    if not settings.canva_client_id:
        logger.warning("image.canva_not_configured")
        return _placeholder(prompt)
    logger.warning("image.canva_oauth_not_implemented")
    return _placeholder(prompt)


def _placeholder(prompt: str) -> str:
    text = prompt[:50].replace(" ", "+")
    return f"https://dummyimage.com/{_SD_WIDTH}x{_SD_HEIGHT}/1a202c/ffffff&text={text}"
