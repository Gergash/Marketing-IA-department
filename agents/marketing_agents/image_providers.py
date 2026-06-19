"""Generación de imágenes: Stable Diffusion (A1111), fal.ai, DALL·E, Canva placeholder y dummy."""

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
    image_provider: str | None = None,
) -> str:
    """Return an image URL for the given prompt, with optional text overlay."""
    from gateway.app.core.settings import get_settings
    s = get_settings()
    provider = (image_provider or s.image_provider).strip().lower()

    if provider == "stable_diffusion":
        return _stable_diffusion(
            prompt,
            s.stable_diffusion_url,
            checkpoint=(s.stable_diffusion_checkpoint or "").strip() or None,
            overlay_text=overlay_text,
            overlay_cta=overlay_cta,
        )
    if provider == "fal" and s.fal_api_key:
        return _fal(
            prompt,
            s.fal_api_key,
            s.fal_model,
            overlay_text=overlay_text,
            overlay_cta=overlay_cta,
        )
    if provider == "fal" and not s.fal_api_key:
        logger.error("image.fal_missing_key")
        return _placeholder(prompt)
    if provider == "openai" and s.openai_api_key:
        return _dalle(prompt, s.openai_api_key)
    if provider == "canva":
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
    """POST a txt2img de A1111/Forge, decodifica PNG, opcionalmente superpone texto y guarda bajo `/static/images/`."""
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
    """Dibuja franja inferior semitransparente, copy envuelto y pastilla de CTA con Pillow."""
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


def _fal(
    prompt: str,
    api_key: str,
    model: str = "fal-ai/flux-pro/v1.1",
    *,
    overlay_text: str | None = None,
    overlay_cta: str | None = None,
) -> str:
    """Genera imagen con fal.ai (Flux pro u otros modelos) y la guarda en static/images/."""
    import os
    import httpx

    os.environ.setdefault("FAL_KEY", api_key)

    try:
        import fal_client  # pip install fal-client
    except ImportError:
        logger.error("image.fal_missing_sdk", hint="pip install fal-client")
        return _placeholder(prompt)

    try:
        result = fal_client.run(
            model,
            arguments={
                "prompt": prompt[:2000],
                "image_size": "landscape_16_9",  # 1024×576 — ideal para redes sociales
                "num_inference_steps": 28,
                "num_images": 1,
                "enable_safety_checker": False,
            },
        )
        image_url: str = result["images"][0]["url"]
        logger.info("image.fal_generated", model=model, url=image_url[:80])
    except Exception as exc:
        logger.error("image.fal_api_error", error=str(exc))
        return _placeholder(prompt)

    try:
        img_resp = httpx.get(image_url, timeout=60, follow_redirects=True)
        img_resp.raise_for_status()
        raw = img_resp.content

        if overlay_text:
            raw = _add_text_overlay(raw, overlay_text, overlay_cta)

        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"fal_{uuid.uuid4().hex}.png"
        (_STATIC_DIR / filename).write_bytes(raw)
        url = f"http://localhost:8000/static/images/{filename}"
        logger.info("image.fal_saved", url=url)
        return url
    except Exception as exc:
        logger.error("image.fal_download_error", error=str(exc))
        return _placeholder(prompt)


def _dalle(prompt: str, api_key: str) -> str:
    """Genera imagen con DALL·E 3 y devuelve la URL remota de OpenAI."""
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
    """Placeholder: Canva requiere OAuth; devuelve placeholder si no está implementado."""
    if not settings.canva_client_id:
        logger.warning("image.canva_not_configured")
        return _placeholder(prompt)
    logger.warning("image.canva_oauth_not_implemented")
    return _placeholder(prompt)


def _placeholder(prompt: str) -> str:
    """Genera imagen placeholder local con Pillow para desarrollo sin GPU ni APIs."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (_SD_WIDTH, _SD_HEIGHT), color=(26, 32, 44))
        draw = ImageDraw.Draw(img)

        try:
            font_big = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size=22)
            font_small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size=15)
        except Exception:
            font_big = ImageFont.load_default()
            font_small = font_big

        label = "[MOCK IMAGE — sin GPU]"
        draw.text((20, 20), label, font=font_big, fill=(255, 130, 0))

        wrapped = textwrap.fill(prompt[:200], width=70)
        draw.text((20, 60), wrapped, font=font_small, fill=(200, 200, 200))

        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"mock_{uuid.uuid4().hex}.png"
        img.save(_STATIC_DIR / filename, format="PNG")
        url = f"http://localhost:8000/static/images/{filename}"
        logger.info("image.placeholder_generated", url=url)
        return url
    except Exception as exc:
        logger.warning("image.placeholder_fallback", error=str(exc))
        text = prompt[:50].replace(" ", "+")
        return f"https://dummyimage.com/{_SD_WIDTH}x{_SD_HEIGHT}/1a202c/ffffff&text={text}"
