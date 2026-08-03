"""Cliente HTTP mínimo para Venice.ai (imagen síncrona + video async queue/retrieve).

API real: https://api.venice.ai/api/v1 — sin SDKs de terceros.
Docs: https://docs.venice.ai/guides/media/image-generation
      https://docs.venice.ai/guides/media/video-generation

Sizing (modelo-específico):
- Pixel: venice-sd35, qwen-image → width/height (máx 1280 por lado)
- Aspect: qwen-image-2 → aspect_ratio
- Resolution-tier: nano-banana*, gpt-image-2 → aspect_ratio + resolution (1K|2K|4K)
"""

from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_BASE = "https://api.venice.ai/api/v1"
_VIDEO_INITIAL_BACKOFF_S = 5.0
_VIDEO_MAX_BACKOFF_S = 30.0
_STATIC_VIDEOS = Path(__file__).resolve().parents[2] / "static" / "videos"

# Máximo documentado en POST /image/generate para width/height.
_PIXEL_MAX_SIDE = 1280

# Modelos con aspect_ratio (sin width/height).
_ASPECT_RATIO_MODELS = (
    "qwen-image-2",
    "gpt-image-2",
    "nano-banana",
    "nano-banana-2",
    "nano-banana-pro",
)

# Subconjunto que además acepta resolution: 1K | 2K | 4K.
_RESOLUTION_TIER_MODELS = (
    "gpt-image-2",
    "nano-banana",
    "nano-banana-2",
    "nano-banana-pro",
)

# promptCharacterLimit por familia (API: venice-sd35 = 1500; Nano Banana ≈ 7500).
_PROMPT_LIMIT_DEFAULT = 1500
_PROMPT_LIMITS: dict[str, int] = {
    "venice-sd35": 1500,
    "qwen-image": 1500,
    "qwen-image-2": 4000,
    "gpt-image-2": 4000,
    "nano-banana": 7500,
    "nano-banana-2": 7500,
    "nano-banana-pro": 7500,
    "z-image-turbo": 1500,
    "flux-2-dev": 1500,
    "flux-2-max": 1500,
}


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _normalize_base(base_url: str) -> str:
    base = (base_url or _DEFAULT_BASE).rstrip("/")
    # Compat: usuarios a veces ponen https://api.venice.ai/v1 (incorrecto).
    if base.endswith("/v1") and "/api/v1" not in base:
        base = base[: -len("/v1")] + "/api/v1"
    return base


def venice_aspect_ratio(width: int, height: int) -> str:
    """Mapea dimensiones a un aspect_ratio Venice conocido."""
    if height <= 0:
        return "1:1"
    ratio = width / height
    candidates = {
        "9:16": 9 / 16,
        "16:9": 16 / 9,
        "1:1": 1.0,
        "4:5": 4 / 5,
        "3:4": 3 / 4,
        "4:3": 4 / 3,
    }
    best = min(candidates.items(), key=lambda kv: abs(kv[1] - ratio))
    return best[0]


def _model_id(model: str) -> str:
    return (model or "").strip().lower()


def _uses_aspect_ratio(model: str) -> bool:
    mid = _model_id(model)
    return any(token in mid for token in _ASPECT_RATIO_MODELS)


def _uses_resolution_tier(model: str) -> bool:
    mid = _model_id(model)
    return any(token in mid for token in _RESOLUTION_TIER_MODELS)


def prompt_limit_for_model(model: str) -> int:
    """Tope de caracteres del prompt según el modelo Venice."""
    mid = _model_id(model)
    for key, limit in _PROMPT_LIMITS.items():
        if key in mid:
            return limit
    return _PROMPT_LIMIT_DEFAULT


def truncate_prompt(prompt: str, model: str) -> str:
    """Recorta el prompt al límite del modelo (deja margen de 20 chars)."""
    text = (prompt or "").strip()
    limit = max(200, prompt_limit_for_model(model) - 20)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def clamp_pixel_dimensions(
    width: int,
    height: int,
    *,
    max_side: int = _PIXEL_MAX_SIDE,
) -> tuple[int, int]:
    """Escala width/height para que ambos lados queden en [512, max_side], múltiplos de 8."""
    w = max(1, int(width))
    h = max(1, int(height))
    scale = min(1.0, max_side / w, max_side / h)
    w2 = int(round(w * scale))
    h2 = int(round(h * scale))
    w2 = max(512, min(max_side, (w2 // 8) * 8))
    h2 = max(512, min(max_side, (h2 // 8) * 8))
    # Tras redondeo a múltiplo de 8, re-clamp si hiciera falta
    if w2 > max_side:
        w2 = (max_side // 8) * 8
    if h2 > max_side:
        h2 = (max_side // 8) * 8
    return w2, h2


def normalize_resolution(resolution: str | None) -> str:
    """Normaliza a 1K | 2K | 4K (default 2K)."""
    raw = (resolution or "2K").strip().upper().replace(" ", "")
    if raw in {"1K", "2K", "4K"}:
        return raw
    # Aliases frecuentes
    if raw in {"1", "1024", "HD"}:
        return "1K"
    if raw in {"2", "2048"}:
        return "2K"
    if raw in {"4", "4096", "UHD"}:
        return "4K"
    return "2K"


def generate_image_bytes(
    prompt: str,
    *,
    api_key: str,
    base_url: str = _DEFAULT_BASE,
    model: str = "venice-sd35",
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str | None = None,
    style_preset: str | None = None,
    resolution: str | None = None,
    fmt: str = "png",
    timeout_s: float = 180.0,
) -> bytes:
    """POST /image/generate → bytes de imagen (decodifica base64 del JSON)."""
    import httpx

    if not api_key.strip():
        raise RuntimeError("venice_image_failed: missing API key")

    model_used = (model or "venice-sd35").strip()
    base = _normalize_base(base_url)
    safe_prompt = truncate_prompt(prompt, model_used)

    payload: dict[str, Any] = {
        "model": model_used,
        "prompt": safe_prompt,
        "format": fmt,
        "safe_mode": True,
    }

    if _uses_resolution_tier(model_used):
        # Google Nano Banana / GPT Image vía Venice: aspect_ratio + resolution.
        payload["aspect_ratio"] = venice_aspect_ratio(width, height)
        payload["resolution"] = normalize_resolution(resolution)
    elif _uses_aspect_ratio(model_used):
        payload["aspect_ratio"] = venice_aspect_ratio(width, height)
    else:
        # venice-sd35 y similares: width/height ≤ 1280.
        w, h = clamp_pixel_dimensions(width, height)
        payload["width"] = w
        payload["height"] = h
        if (negative_prompt or "").strip():
            neg = negative_prompt.strip()
        else:
            from .visual_prompt_guards import NO_TEXT_NEGATIVE

            neg = NO_TEXT_NEGATIVE
        payload["negative_prompt"] = neg

    if style_preset and not _uses_resolution_tier(model_used):
        # style_preset es más fiable en modelos pixel/aspect nativos Venice.
        payload["style_preset"] = style_preset

    logger.info(
        "venice.image_request",
        model=model_used,
        prompt_chars=len(safe_prompt),
        prompt_limit=prompt_limit_for_model(model_used),
        sizing={
            k: payload[k]
            for k in ("width", "height", "aspect_ratio", "resolution")
            if k in payload
        },
    )

    try:
        resp = httpx.post(
            f"{base}/image/generate",
            headers=_auth_headers(api_key),
            json=payload,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        detail = _http_detail(exc)
        logger.error("venice.image_error", error=detail, model=model_used)
        raise RuntimeError(f"venice_image_failed: {detail}") from exc

    images = data.get("images") or []
    if not images:
        raise RuntimeError("venice_image_failed: empty images[] in response")

    raw_b64 = images[0]
    if isinstance(raw_b64, dict):
        raw_b64 = raw_b64.get("b64_json") or raw_b64.get("base64") or ""
    if not isinstance(raw_b64, str) or not raw_b64:
        raise RuntimeError("venice_image_failed: unexpected image payload shape")

    # Algunos wrappers OpenAI-compat usan data URI.
    if raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[-1]

    try:
        return base64.b64decode(raw_b64)
    except Exception as exc:
        raise RuntimeError(f"venice_image_failed: invalid base64: {exc}") from exc


def generate_video_bytes(
    prompt: str,
    *,
    api_key: str,
    base_url: str = _DEFAULT_BASE,
    model: str = "wan-2.5-preview-text-to-video",
    duration: str = "5s",
    resolution: str = "720p",
    aspect_ratio: str | None = "9:16",
    image_url: str | None = None,
    negative_prompt: str | None = None,
    max_wait_seconds: int = 600,
) -> bytes:
    """Queue + poll /video/retrieve hasta obtener MP4 (bytes)."""
    import httpx

    if not api_key.strip():
        raise RuntimeError("venice_video_failed: missing API key")

    base = _normalize_base(base_url)
    headers = _auth_headers(api_key)
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt[:2500],
        "duration": duration,
        "resolution": resolution,
    }
    if aspect_ratio and "image-to-video" not in model.lower():
        # i2v suele derivar el ratio de la imagen; aspect_ratio puede rechazarse.
        payload["aspect_ratio"] = aspect_ratio
    if image_url:
        payload["image_url"] = image_url
        # Si el modelo por defecto es t2v pero hay imagen, preferir i2v salvo override explícito.
        if "image-to-video" not in model.lower() and "text-to-video" in model.lower():
            payload["model"] = model.replace("text-to-video", "image-to-video")
            model = payload["model"]
            payload.pop("aspect_ratio", None)
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt

    try:
        queue_resp = httpx.post(
            f"{base}/video/queue",
            headers=headers,
            json=payload,
            timeout=60,
        )
        queue_resp.raise_for_status()
        queued = queue_resp.json()
    except Exception as exc:
        detail = _http_detail(exc)
        logger.error("venice.video_queue_error", error=detail, model=model)
        raise RuntimeError(f"venice_video_failed:queue: {detail}") from exc

    queue_id = queued.get("queue_id")
    model_used = queued.get("model") or model
    download_url = queued.get("download_url")
    if not queue_id:
        raise RuntimeError(f"venice_video_failed:queue: missing queue_id in {queued!r}")

    logger.info("venice.video_queued", queue_id=queue_id, model=model_used)

    start = time.monotonic()
    backoff = _VIDEO_INITIAL_BACKOFF_S
    while True:
        try:
            poll_resp = httpx.post(
                f"{base}/video/retrieve",
                headers=headers,
                json={"model": model_used, "queue_id": queue_id},
                timeout=120,
            )
            poll_resp.raise_for_status()
        except Exception as exc:
            detail = _http_detail(exc)
            logger.error("venice.video_retrieve_error", error=detail, queue_id=queue_id)
            raise RuntimeError(f"venice_video_failed:retrieve: {detail}") from exc

        ctype = (poll_resp.headers.get("Content-Type") or "").lower()
        if "video/mp4" in ctype or "application/octet-stream" in ctype:
            raw = poll_resp.content
            if raw:
                _maybe_complete(base, headers, model_used, queue_id)
                return raw

        try:
            status_payload = poll_resp.json()
        except Exception:
            status_payload = {}

        status = str(status_payload.get("status") or "").upper()
        if status == "COMPLETED":
            url = download_url or status_payload.get("download_url")
            if not url:
                raise RuntimeError("venice_video_failed: COMPLETED without download_url")
            try:
                dl = httpx.get(url, timeout=180, follow_redirects=True)
                dl.raise_for_status()
                _maybe_complete(base, headers, model_used, queue_id)
                return dl.content
            except Exception as exc:
                raise RuntimeError(f"venice_video_failed:download: {exc}") from exc

        if status in {"FAILED", "ERROR", "CANCELLED"}:
            raise RuntimeError(f"venice_video_failed: status={status} detail={status_payload}")

        if time.monotonic() - start > max_wait_seconds:
            raise TimeoutError(
                f"venice_video_timeout: exceeded {max_wait_seconds}s queue_id={queue_id}"
            )

        time.sleep(backoff)
        backoff = min(backoff * 2, _VIDEO_MAX_BACKOFF_S)


def save_video_bytes(raw: bytes, *, prefix: str = "venice") -> str:
    """Persiste MP4 en static/videos/ y devuelve URL local del gateway."""
    _STATIC_VIDEOS.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex}.mp4"
    (_STATIC_VIDEOS / filename).write_bytes(raw)
    return f"http://localhost:8000/static/videos/{filename}"


def image_url_to_data_uri(image_url: str) -> str:
    """Convierte URL local/remota a data URI para /video/queue (evita depender de ngrok)."""
    import httpx

    parsed = urlparse(image_url)
    local_roots = (
        Path(__file__).resolve().parents[2] / "static",
    )

    # URL del gateway local → leer fichero del disco.
    if parsed.scheme in ("http", "https") and parsed.hostname in {"localhost", "127.0.0.1"}:
        path = parsed.path or ""
        if "/static/" in path:
            rel = path.split("/static/", 1)[-1]
            file_path = local_roots[0] / rel
            if file_path.is_file():
                raw = file_path.read_bytes()
                mime = "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
                if file_path.suffix.lower() == ".webp":
                    mime = "image/webp"
                return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    if image_url.startswith("data:"):
        return image_url

    resp = httpx.get(image_url, timeout=90, follow_redirects=True)
    resp.raise_for_status()
    ctype = (resp.headers.get("Content-Type") or "image/png").split(";")[0].strip()
    if not ctype.startswith("image/"):
        ctype = "image/png"
    return f"data:{ctype};base64,{base64.b64encode(resp.content).decode('ascii')}"


def _maybe_complete(base: str, headers: dict[str, str], model: str, queue_id: str) -> None:
    """Best-effort cleanup en Venice tras descargar el MP4."""
    import httpx

    try:
        httpx.post(
            f"{base}/video/complete",
            headers=headers,
            json={"model": model, "queue_id": queue_id},
            timeout=30,
        )
    except Exception as exc:
        logger.warning("venice.video_complete_skipped", error=str(exc), queue_id=queue_id)


def _http_detail(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)
    body = (getattr(response, "text", None) or "").strip()
    if len(body) > 1500:
        body = body[:1500] + "…"
    return f"{exc} | body={body}" if body else str(exc)
