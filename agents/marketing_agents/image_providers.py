from __future__ import annotations

import base64
import uuid
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "images"
_SD_WIDTH = 768
_SD_HEIGHT = 512
_SD_STEPS = 20
_DALLE_SIZE = "1792x1024"


def generate_image(prompt: str) -> str:
    """Return an image URL for the given prompt."""
    from gateway.app.core.settings import get_settings
    s = get_settings()

    if s.image_provider == "stable_diffusion":
        return _stable_diffusion(
            prompt,
            s.stable_diffusion_url,
            checkpoint=(s.stable_diffusion_checkpoint or "").strip() or None,
        )
    if s.image_provider == "openai" and s.openai_api_key:
        return _dalle(prompt, s.openai_api_key)
    if s.image_provider == "canva":
        return _canva(prompt, s)
    return _placeholder(prompt)


def _stable_diffusion(prompt: str, sd_url: str, *, checkpoint: str | None) -> str:
    """
    Llama a la API REST de Automatic1111 / AUTOMATIC1111 WebUI.
    Guarda la imagen en static/images/ y devuelve la URL local.
    La imagen queda disponible en http://localhost:8000/static/images/<uuid>.png

    Si `checkpoint` está definido, se envía override_settings.sd_model_checkpoint para forzar
    el modelo (debe coincidir con el nombre en el desplegable de checkpoints del WebUI).
    """
    import httpx

    payload: dict = {
        "prompt": prompt[:500],
        "negative_prompt": "blurry, low quality, text, watermark, signature",
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
        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        ((_STATIC_DIR) / filename).write_bytes(raw)
        url = f"http://localhost:8000/static/images/{filename}"
        logger.info("image.sd_generated", url=url)
        return url
    except Exception as exc:
        logger.error("image.sd_error", error=str(exc))
        return _placeholder(prompt)


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
    # Canva Connect API requiere OAuth 2.0 + brand template ID.
    if not settings.canva_client_id:
        logger.warning("image.canva_not_configured")
        return _placeholder(prompt)
    logger.warning("image.canva_oauth_not_implemented")
    return _placeholder(prompt)


def _placeholder(prompt: str) -> str:
    text = prompt[:50].replace(" ", "+")
    return f"https://dummyimage.com/{_SD_WIDTH}x{_SD_HEIGHT}/1a202c/ffffff&text={text}"
