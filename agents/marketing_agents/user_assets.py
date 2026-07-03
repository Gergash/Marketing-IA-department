"""Carga y preparación de fotos de usuario para Design-as-Code (sin destruir la capa base)."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import structlog

from .image_specs import ImageSpec

logger = structlog.get_logger(__name__)

_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"
_UPLOADS_DIR = _STATIC_ROOT / "uploads"
_IMAGES_DIR = _STATIC_ROOT / "images"

ALLOWED_UPLOAD_MIME = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def uploads_dir() -> Path:
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return _UPLOADS_DIR


def local_url_for_upload(filename: str) -> str:
    return f"http://localhost:8000/static/uploads/{filename}"


def resolve_local_path(asset_url: str) -> Path | None:
    """Mapea URL servida por FastAPI static a ruta en disco."""
    if "/static/" in asset_url:
        rel = asset_url.split("/static/", 1)[1]
        return _STATIC_ROOT / rel.replace("\\", "/")
    if asset_url.startswith("/static/"):
        return _STATIC_ROOT / asset_url.removeprefix("/static/").lstrip("/")
    return None


def load_asset_bytes(asset_url: str) -> bytes:
    """Lee bytes de una foto subida (local static) o remota."""
    local = resolve_local_path(asset_url)
    if local and local.is_file():
        return local.read_bytes()

    import httpx

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        resp = client.get(asset_url)
        resp.raise_for_status()
        return resp.content


def fit_image_to_spec(raw: bytes, spec: ImageSpec) -> bytes:
    """Escala la foto (cover) al tamaño de la red sin regenerar con IA."""
    from PIL import Image

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    target_w, target_h = spec.width, spec.height
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    cropped = resized.crop((left, top, left + target_w, top + target_h))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


def save_composed_image(raw: bytes, *, prefix: str = "composed") -> tuple[str, int, int]:
    """Guarda PNG compuesto en static/images y devuelve (url, width, height)."""
    from PIL import Image

    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(raw))
    w, h = img.size
    filename = f"{prefix}_{uuid.uuid4().hex}.png"
    (_IMAGES_DIR / filename).write_bytes(raw)
    url = f"http://localhost:8000/static/images/{filename}"
    return url, w, h
