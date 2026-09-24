"""Catálogo de modelos de video Venice (Seedance / Kling / MiniMax / Gemini Omni / Wan).

La API real usa IDs canónicos; aquí resolvemos aliases amigables del UI/.env.
Seedance 2.5: si Venice aún no publica el ID, se mapea a Seedance 2.0 (mejor disponible).

Gemini Omni Flash 1.1: duraciones 4s|6s|8s|10s (no 5s). Ver ``normalize_venice_video_duration``.
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
    # Gemini Omni Flash (Google vía Venice) — 1.1 es el ID canónico actual
    "gemini-omni-flash": "gemini-omni-flash-1-1-text-to-video",
    "gemini-omni-flash-1-1": "gemini-omni-flash-1-1-text-to-video",
    "gemini-omni-flash-1.1": "gemini-omni-flash-1-1-text-to-video",
    "gemini-omni": "gemini-omni-flash-1-1-text-to-video",
    "gemini-omni-flash-text-to-video": "gemini-omni-flash-1-1-text-to-video",
    "gemini-omni-flash-1-1-text-to-video": "gemini-omni-flash-1-1-text-to-video",
}

_I2V_FROM_T2V: dict[str, str] = {
    "seedance-2-0-text-to-video": "seedance-2-0-image-to-video",
    "seedance-2-0-fast-text-to-video": "seedance-2-0-fast-image-to-video",
    "kling-o3-standard-text-to-video": "kling-o3-standard-image-to-video",
    "kling-o3-pro-text-to-video": "kling-o3-pro-image-to-video",
    "minimax-hailuo-02-text-to-video": "minimax-hailuo-02-image-to-video",
    "wan-2.5-preview-text-to-video": "wan-2.5-preview-image-to-video",
    "gemini-omni-flash-1-1-text-to-video": "gemini-omni-flash-1-1-image-to-video",
    "gemini-omni-flash-text-to-video": "gemini-omni-flash-image-to-video",
}

# Duraciones admitidas por familia (snap si el .env pide un valor inválido)
_GEMINI_OMNI_DURATIONS = ("4s", "6s", "8s", "10s")
_DEFAULT_DURATIONS = ("5s", "10s")

# Modelos listados en UI
VENICE_VIDEO_MODEL_OPTIONS: list[dict[str, str]] = [
    {
        "id": "gemini-omni-flash-1-1",
        "label": "Gemini Omni Flash 1.1 (text-to-video)",
        "family": "gemini",
    },
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
        mid = "gemini-omni-flash-1-1-text-to-video"
    else:
        mid = _T2V_ALIASES.get(raw, raw)
        # Si ya viene como i2v / r2v / v2v explícito, respetarlo
        if any(tok in raw for tok in ("image-to-video", "reference-to-video", "video-to-video")):
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


def is_gemini_omni_video_model(model_id: str) -> bool:
    return "gemini-omni" in (model_id or "").lower()


def normalize_venice_video_duration(duration: str | None, model_id: str) -> str:
    """Ajusta duración al set permitido del modelo (Gemini Omni: 4/6/8/10s; resto: 5/10s)."""
    raw = (duration or "").strip().lower().replace(" ", "")
    if raw and not raw.endswith("s"):
        raw = f"{raw}s"
    allowed = _GEMINI_OMNI_DURATIONS if is_gemini_omni_video_model(model_id) else _DEFAULT_DURATIONS
    if raw in allowed:
        return raw
    try:
        sec = float((raw or "5").rstrip("s"))
    except ValueError:
        return "6s" if is_gemini_omni_video_model(model_id) else "5s"
    # Empate (p.ej. 5s → 4s|6s): preferir el valor superior (más cerca del clip “estándar”).
    return min(allowed, key=lambda d: (abs(float(d.rstrip("s")) - sec), -float(d.rstrip("s"))))


def prefers_text_to_video_full_clip(alias: str) -> bool:
    """True si en mode=full conviene NO anclar a still (puro text-to-video)."""
    raw = (alias or "").strip().lower()
    mid = resolve_venice_video_model(raw, for_image=False)
    if "text-to-video" in raw:
        return True
    return is_gemini_omni_video_model(mid)
