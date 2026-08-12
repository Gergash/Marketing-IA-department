"""Catálogo de modelos de video Venice (Seedance / Kling O3 / MiniMax).

La API real usa IDs canónicos; aquí resolvemos aliases amigables del UI/.env.
Seedance 2.5: si Venice aún no publica el ID, se mapea a Seedance 2.0 (mejor disponible).
"""

from __future__ import annotations

# Aliases UI / .env → model ID Venice (text-to-video por defecto)
_T2V_ALIASES: dict[str, str] = {
    "seedance-2.5": "seedance-2-0-text-to-video",
    "seedance-2-5": "seedance-2-0-text-to-video",
    "seedance-2.5-text-to-video": "seedance-2-0-text-to-video",
    "seedance-2-5-text-to-video": "seedance-2-0-text-to-video",
    "seedance-2.0": "seedance-2-0-text-to-video",
    "seedance-2-0": "seedance-2-0-text-to-video",
    "seedance-2-0-text-to-video": "seedance-2-0-text-to-video",
    "seedance-2-0-fast-text-to-video": "seedance-2-0-fast-text-to-video",
    "kling-o3": "kling-o3-standard-text-to-video",
    "kling-o3-standard": "kling-o3-standard-text-to-video",
    "kling-o3-standard-text-to-video": "kling-o3-standard-text-to-video",
    "kling-o3-pro": "kling-o3-pro-text-to-video",
    "kling-o3-pro-text-to-video": "kling-o3-pro-text-to-video",
    "minimax-h3": "minimax-hailuo-02-text-to-video",
    "minimax": "minimax-hailuo-02-text-to-video",
    "minimax-hailuo": "minimax-hailuo-02-text-to-video",
    "minimax-hailuo-02-text-to-video": "minimax-hailuo-02-text-to-video",
    "wan-2.5": "wan-2.5-preview-text-to-video",
    "wan-2.5-preview-text-to-video": "wan-2.5-preview-text-to-video",
}

_I2V_FROM_T2V: dict[str, str] = {
    "seedance-2-0-text-to-video": "seedance-2-0-image-to-video",
    "seedance-2-0-fast-text-to-video": "seedance-2-0-fast-image-to-video",
    "kling-o3-standard-text-to-video": "kling-o3-standard-image-to-video",
    "kling-o3-pro-text-to-video": "kling-o3-pro-image-to-video",
    "minimax-hailuo-02-text-to-video": "minimax-hailuo-02-image-to-video",
    "wan-2.5-preview-text-to-video": "wan-2.5-preview-image-to-video",
}

# Modelos listados en UI
VENICE_VIDEO_MODEL_OPTIONS: list[dict[str, str]] = [
    {"id": "seedance-2.5", "label": "Seedance 2.5 (→ 2.0 si no disponible)", "family": "seedance"},
    {"id": "seedance-2.0", "label": "Seedance 2.0", "family": "seedance"},
    {"id": "kling-o3", "label": "Kling O3 Standard", "family": "kling"},
    {"id": "kling-o3-pro", "label": "Kling O3 Pro", "family": "kling"},
    {"id": "minimax-h3", "label": "MiniMax Hailuo / H3", "family": "minimax"},
]


def resolve_venice_video_model(name: str, *, for_image: bool = False) -> str:
    """Resuelve alias → ID Venice. Si for_image, convierte t2v → i2v cuando aplica."""
    raw = (name or "").strip().lower()
    if not raw:
        mid = "seedance-2-0-text-to-video"
    else:
        mid = _T2V_ALIASES.get(raw, raw)
        # Si ya viene como i2v explícito, respetarlo
        if "image-to-video" in raw:
            return raw
    if for_image:
        if "image-to-video" in mid:
            return mid
        return _I2V_FROM_T2V.get(mid, mid.replace("text-to-video", "image-to-video"))
    return mid


def model_supports_aspect_ratio(model_id: str) -> bool:
    mid = (model_id or "").lower()
    if "image-to-video" in mid:
        return False  # ratio derivado de la imagen
    return True
