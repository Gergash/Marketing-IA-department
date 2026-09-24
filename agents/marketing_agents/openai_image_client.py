"""Cliente HTTP mínimo para OpenAI Images API (gpt-image-2 directo).

Base: https://api.openai.com/v1
Docs: https://developers.openai.com/api/docs/guides/image-generation

Separado de ``OPENAI_API_KEY`` / OpenRouter (LLM de texto): usa
``OPENAI_IMAGE_API_KEY`` + ``OPENAI_IMAGE_API_BASE``.

- Generate: POST /images/generations (JSON) → data[0].b64_json
- Edit:     POST /images/edits (multipart) → data[0].b64_json
"""

from __future__ import annotations

import base64
import io
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_BASE = "https://api.openai.com/v1"
_PROMPT_LIMIT = 32000  # GPT image models

# Tamaños “estándar” documentados (gpt-image-2 también acepta WIDTHxHEIGHT arbitrario;
# usamos el set cerrado para coste predecible y luego Pillow reencuadra al ImageSpec).
_STANDARD_SIZES: tuple[tuple[str, float], ...] = (
    ("1024x1024", 1.0),
    ("1024x1536", 1024 / 1536),
    ("1536x1024", 1536 / 1024),
)


def _normalize_base(base_url: str) -> str:
    base = (base_url or _DEFAULT_BASE).rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1" if not base.endswith("/v1") else base


def _auth_headers(api_key: str, *, json_body: bool = True) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def truncate_prompt(prompt: str, *, limit: int = _PROMPT_LIMIT) -> str:
    text = (prompt or "").strip()
    cap = max(200, limit - 20)
    if len(text) <= cap:
        return text
    return text[: cap - 1].rstrip() + "…"


def openai_image_size(width: int, height: int) -> str:
    """Mapea ImageSpec al size OpenAI más cercano (1024x1024 | 1024x1536 | 1536x1024)."""
    w = max(1, int(width))
    h = max(1, int(height))
    ratio = w / h
    best = min(_STANDARD_SIZES, key=lambda kv: abs(kv[1] - ratio))
    return best[0]


def normalize_quality(quality: str | None) -> str:
    raw = (quality or "high").strip().lower()
    if raw in {"low", "medium", "high", "auto"}:
        return raw
    return "high"


def normalize_background(background: str | None) -> str:
    raw = (background or "opaque").strip().lower()
    if raw in {"opaque", "transparent", "auto"}:
        return raw
    return "opaque"


def _http_detail(exc: BaseException) -> str:
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            body = resp.text
        except Exception:
            body = ""
        return f"HTTP {getattr(resp, 'status_code', '?')}: {body[:500]}"
    return str(exc)


def _decode_b64_image(data: dict[str, Any]) -> bytes:
    items = data.get("data") or []
    if not items:
        raise RuntimeError("openai_image_failed: empty data[] in response")
    item = items[0]
    raw_b64 = item if isinstance(item, str) else (item.get("b64_json") or "")
    if not isinstance(raw_b64, str) or not raw_b64:
        # dall-e-3 style URL — no soportado en este cliente (gpt-image-* = b64)
        url = item.get("url") if isinstance(item, dict) else None
        if url:
            raise RuntimeError(
                "openai_image_failed: got url instead of b64_json "
                "(use gpt-image-2; dall-e-3 belongs to IMAGE_PROVIDER=openai)"
            )
        raise RuntimeError("openai_image_failed: missing b64_json in response")
    if raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[-1]
    try:
        return base64.b64decode(raw_b64)
    except Exception as exc:
        raise RuntimeError(f"openai_image_failed: invalid base64: {exc}") from exc


def _log_usage(data: dict[str, Any], *, op: str, model: str) -> None:
    usage = data.get("usage") or {}
    if not usage:
        return
    logger.info(
        "openai_image.usage",
        op=op,
        model=model,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
        size=data.get("size"),
        quality=data.get("quality"),
    )


def _prepare_edit_source(image_bytes: bytes) -> tuple[bytes, str, str]:
    """PNG/JPEG RGB <50MB para /images/edits."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"openai_image_edit_failed: cannot decode source: {exc}") from exc

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    out = buf.getvalue()
    if len(out) >= 50 * 1024 * 1024:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        out = buf.getvalue()
        if len(out) >= 50 * 1024 * 1024:
            raise RuntimeError("openai_image_edit_failed: encoded image exceeds 50MB")
        return out, "image.jpg", "image/jpeg"
    return out, "image.png", "image/png"


def generate_image_bytes(
    prompt: str,
    *,
    api_key: str,
    base_url: str = _DEFAULT_BASE,
    model: str = "gpt-image-2",
    width: int = 1024,
    height: int = 1024,
    quality: str | None = "high",
    background: str | None = "opaque",
    timeout_s: float = 180.0,
) -> bytes:
    """POST /images/generations → bytes PNG (b64_json)."""
    import httpx

    if not (api_key or "").strip():
        raise RuntimeError("openai_image_failed: missing API key")

    model_used = (model or "gpt-image-2").strip()
    base = _normalize_base(base_url)
    safe_prompt = truncate_prompt(prompt)
    size = openai_image_size(width, height)
    q = normalize_quality(quality)
    bg = normalize_background(background)

    payload: dict[str, Any] = {
        "model": model_used,
        "prompt": safe_prompt,
        "size": size,
        "quality": q,
        "background": bg,
        "output_format": "png",
        "n": 1,
    }

    logger.info(
        "openai_image.generate_request",
        model=model_used,
        size=size,
        quality=q,
        prompt_chars=len(safe_prompt),
        target=f"{width}x{height}",
    )

    try:
        resp = httpx.post(
            f"{base}/images/generations",
            headers=_auth_headers(api_key),
            json=payload,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        detail = _http_detail(exc)
        logger.error("openai_image.generate_error", error=detail, model=model_used)
        raise RuntimeError(f"openai_image_failed: {detail}") from exc

    _log_usage(data, op="generate", model=model_used)
    return _decode_b64_image(data)


def edit_image_bytes(
    image_bytes: bytes,
    prompt: str,
    *,
    api_key: str,
    base_url: str = _DEFAULT_BASE,
    model: str = "gpt-image-2",
    width: int = 1024,
    height: int = 1024,
    quality: str | None = "high",
    background: str | None = "opaque",
    timeout_s: float = 240.0,
) -> bytes:
    """POST /images/edits (multipart) → bytes PNG (b64_json).

    gpt-image-2 procesa inputs a alta fidelidad por defecto (no enviar input_fidelity).
    """
    import httpx

    if not (api_key or "").strip():
        raise RuntimeError("openai_image_edit_failed: missing API key")
    if not image_bytes:
        raise RuntimeError("openai_image_edit_failed: empty source image")

    model_used = (model or "gpt-image-2").strip()
    base = _normalize_base(base_url)
    safe_prompt = truncate_prompt(prompt)
    size = openai_image_size(width, height)
    q = normalize_quality(quality)
    bg = normalize_background(background)
    encoded, filename, mime = _prepare_edit_source(image_bytes)

    form: dict[str, Any] = {
        "model": model_used,
        "prompt": safe_prompt,
        "size": size,
        "quality": q,
        "background": bg,
        "output_format": "png",
        "n": "1",
    }
    files = {"image": (filename, encoded, mime)}

    logger.info(
        "openai_image.edit_request",
        model=model_used,
        size=size,
        quality=q,
        prompt_chars=len(safe_prompt),
        source_bytes=len(encoded),
        source_mime=mime,
    )

    try:
        resp = httpx.post(
            f"{base}/images/edits",
            headers=_auth_headers(api_key, json_body=False),
            data=form,
            files=files,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        detail = _http_detail(exc)
        logger.error("openai_image.edit_error", error=detail, model=model_used)
        raise RuntimeError(f"openai_image_edit_failed: {detail}") from exc

    _log_usage(data, op="edit", model=model_used)
    return _decode_b64_image(data)
