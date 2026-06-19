"""Generación de imágenes: Stable Diffusion (A1111), fal.ai, DALL·E, Canva placeholder y dummy."""

from __future__ import annotations

import base64
import io
import textwrap
import uuid
from pathlib import Path

import structlog

from .image_specs import fal_image_size_arg, resolve_image_spec
from .overlay_text import build_overlay_lines, pick_font_pair, wrap_for_width

logger = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "images"
_SD_STEPS = 20
_DALLE_SIZE = "1792x1024"


def generate_image(
    prompt: str,
    *,
    overlay_text: str | None = None,
    overlay_subline: str | None = None,
    overlay_cta: str | None = None,
    image_provider: str | None = None,
    red_social: str = "instagram",
    content_format: str = "feed",
) -> tuple[str, int, int]:
    """Return (image URL, width, height) for the given prompt."""
    from gateway.app.core.settings import get_settings

    s = get_settings()
    provider = (image_provider or s.image_provider).strip().lower()
    spec = resolve_image_spec(red_social, content_format)

    if provider == "stable_diffusion":
        url = _stable_diffusion(
            prompt,
            s.stable_diffusion_url,
            spec=spec,
            checkpoint=(s.stable_diffusion_checkpoint or "").strip() or None,
            overlay_text=overlay_text,
            overlay_subline=overlay_subline,
            overlay_cta=overlay_cta,
            red_social=red_social,
        )
        return url, spec.width, spec.height
    if provider == "fal" and s.fal_api_key:
        url = _fal(
            prompt,
            s.fal_api_key,
            s.fal_model,
            spec=spec,
            overlay_text=overlay_text,
            overlay_subline=overlay_subline,
            overlay_cta=overlay_cta,
            red_social=red_social,
        )
        return url, spec.width, spec.height
    if provider == "fal" and not s.fal_api_key:
        logger.error("image.fal_missing_key")
        url = _placeholder(prompt, spec=spec)
        return url, spec.width, spec.height
    if provider == "openai" and s.openai_api_key:
        url = _dalle(prompt, s.openai_api_key)
        return url, spec.width, spec.height
    if provider == "canva":
        url = _canva(prompt, s)
        return url, spec.width, spec.height
    url = _placeholder(prompt, spec=spec)
    return url, spec.width, spec.height


def _stable_diffusion(
    prompt: str,
    sd_url: str,
    *,
    spec,
    checkpoint: str | None,
    overlay_text: str | None = None,
    overlay_subline: str | None = None,
    overlay_cta: str | None = None,
    red_social: str = "instagram",
) -> str:
    """POST a txt2img de A1111/Forge, decodifica PNG, superpone texto y guarda en `/static/images/`."""
    import httpx

    payload: dict = {
        "prompt": (
            f"{prompt[:400]}. No text, no letters, no watermark, clean composition, "
            "negative space at bottom for text overlay."
        ),
        "negative_prompt": "text, letters, words, watermark, signature, blurry, low quality, deformed, ugly",
        "width": spec.width,
        "height": spec.height,
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
            return _placeholder(prompt, spec=spec)

        raw = base64.b64decode(images[0])

        if overlay_text:
            raw = _add_text_overlay(
                raw,
                overlay_text,
                overlay_subline,
                overlay_cta,
                font_seed=red_social,
            )

        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        (_STATIC_DIR / filename).write_bytes(raw)
        url = f"http://localhost:8000/static/images/{filename}"
        logger.info("image.sd_generated", url=url, size=f"{spec.width}x{spec.height}")
        return url
    except Exception as exc:
        logger.error("image.sd_error", error=str(exc))
        return _placeholder(prompt, spec=spec)


def _add_text_overlay(
    img_bytes: bytes,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    font_seed: str = "instagram",
) -> bytes:
    """Dibuja franja inferior con headline/subline y CTA; tipografía escalada por tamaño de imagen."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    w, h = img.size
    bar_h = max(h // 3, int(h * 0.28))
    base_font = max(14, min(28, w // 42))
    (title_path, title_size), (body_path, body_size) = pick_font_pair(font_seed, base_font)

    try:
        font_title = ImageFont.truetype(title_path, size=title_size)
        font_body = ImageFont.truetype(body_path, size=body_size)
        font_cta = ImageFont.truetype(body_path, size=max(13, body_size - 1))
    except Exception:
        font_title = ImageFont.load_default()
        font_body = font_title
        font_cta = font_title

    draw.rectangle([(0, h - bar_h), (w, h)], fill=(10, 10, 20, 190))

    y = h - bar_h + int(bar_h * 0.08)
    headline_line, subline_line = build_overlay_lines(headline=headline, subline=subline)
    wrapped_headline = wrap_for_width(headline_line, w - 40, font_size=title_size)
    draw.text((20, y), wrapped_headline, font=font_title, fill=(255, 255, 255, 250))
    y += title_size * (wrapped_headline.count("\n") + 1) + 8

    if subline_line:
        wrapped_sub = wrap_for_width(subline_line, w - 40, font_size=body_size)
        draw.text((20, y), wrapped_sub, font=font_body, fill=(230, 230, 240, 235))

    if cta:
        cta_label = f"  {cta[:45]}  "
        cta_y = h - max(32, int(bar_h * 0.18))
        bbox = draw.textbbox((0, 0), cta_label, font=font_cta)
        cta_w = bbox[2] - bbox[0] + 4
        draw.rounded_rectangle(
            [(16, cta_y - 4), (16 + cta_w, cta_y + 22)],
            radius=8,
            fill=(255, 130, 0, 230),
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
    spec,
    overlay_text: str | None = None,
    overlay_subline: str | None = None,
    overlay_cta: str | None = None,
    red_social: str = "instagram",
) -> str:
    """Genera imagen con fal.ai (Flux pro u otros modelos) y la guarda en static/images/."""
    import os

    import httpx

    os.environ.setdefault("FAL_KEY", api_key)

    try:
        import fal_client  # pip install fal-client
    except ImportError:
        logger.error("image.fal_missing_sdk", hint="pip install fal-client")
        return _placeholder(prompt, spec=spec)

    visual_prompt = (
        f"{prompt[:1800]}. No text, no letters, no watermark. "
        f"Aspect ratio {spec.label}. Clean composition with negative space at bottom for overlay."
    )
    try:
        result = fal_client.run(
            model,
            arguments={
                "prompt": visual_prompt,
                "image_size": fal_image_size_arg(spec),
                "num_inference_steps": 28,
                "num_images": 1,
                "enable_safety_checker": False,
            },
        )
        image_url: str = result["images"][0]["url"]
        logger.info(
            "image.fal_generated",
            model=model,
            size=f"{spec.width}x{spec.height}",
            url=image_url[:80],
        )
    except Exception as exc:
        logger.error("image.fal_api_error", error=str(exc))
        return _placeholder(prompt, spec=spec)

    try:
        img_resp = httpx.get(image_url, timeout=60, follow_redirects=True)
        img_resp.raise_for_status()
        raw = img_resp.content

        if overlay_text:
            raw = _add_text_overlay(
                raw,
                overlay_text,
                overlay_subline,
                overlay_cta,
                font_seed=red_social,
            )

        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"fal_{uuid.uuid4().hex}.png"
        (_STATIC_DIR / filename).write_bytes(raw)
        url = f"http://localhost:8000/static/images/{filename}"
        logger.info("image.fal_saved", url=url)
        return url
    except Exception as exc:
        logger.error("image.fal_download_error", error=str(exc))
        return _placeholder(prompt, spec=spec)


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


def _placeholder(prompt: str, *, spec=None) -> str:
    """Genera imagen placeholder local con Pillow para desarrollo sin GPU ni APIs."""
    if spec is None:
        spec = resolve_image_spec("instagram", "feed")
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (spec.width, spec.height), color=(26, 32, 44))
        draw = ImageDraw.Draw(img)

        try:
            font_big = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", size=22)
            font_small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size=15)
        except Exception:
            font_big = ImageFont.load_default()
            font_small = font_big

        label = f"[MOCK — {spec.width}x{spec.height}]"
        draw.text((20, 20), label, font=font_big, fill=(255, 130, 0))

        wrapped = textwrap.fill(prompt[:200], width=max(30, spec.width // 14))
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
        return f"https://dummyimage.com/{spec.width}x{spec.height}/1a202c/ffffff&text={text}"
