"""Dimensiones de imagen por red social y formato de contenido (feed / story)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImageSpec:
    """Tamaño objetivo en píxeles y metadatos para proveedores de imagen."""

    width: int
    height: int
    label: str  # descripción legible, p. ej. "instagram feed 1:1"

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 1.0


# Instagram: feed portrait 4:5 (1080×1350); story/reels 9:16 (1080×1920)
_SPECS: dict[tuple[str, str], ImageSpec] = {
    ("instagram", "feed"): ImageSpec(1080, 1350, "instagram feed 4:5"),
    ("instagram", "story"): ImageSpec(1080, 1920, "instagram story 9:16"),
    ("instagram", "reel"): ImageSpec(1080, 1920, "instagram reel 9:16"),
    ("ig", "feed"): ImageSpec(1080, 1350, "instagram feed 4:5"),
    ("ig", "story"): ImageSpec(1080, 1920, "instagram story 9:16"),
    ("ig", "reel"): ImageSpec(1080, 1920, "instagram reel 9:16"),
    ("facebook", "feed"): ImageSpec(1080, 1350, "facebook feed 4:5"),
    ("facebook", "story"): ImageSpec(1080, 1920, "facebook story 9:16"),
    ("facebook", "reel"): ImageSpec(1080, 1920, "facebook reel 9:16"),
    ("fb", "feed"): ImageSpec(1080, 1350, "facebook feed 4:5"),
    ("linkedin", "feed"): ImageSpec(1200, 627, "linkedin feed 1.91:1"),
    ("linkedin", "story"): ImageSpec(1080, 1920, "linkedin story 9:16"),
    ("x", "feed"): ImageSpec(1200, 675, "x feed 16:9"),
    ("x", "reel"): ImageSpec(1080, 1920, "x video 9:16"),
    ("twitter", "feed"): ImageSpec(1200, 675, "x feed 16:9"),
    ("twitter", "reel"): ImageSpec(1080, 1920, "x video 9:16"),
    ("tiktok", "feed"): ImageSpec(1080, 1920, "tiktok vertical 9:16"),
    ("tiktok", "story"): ImageSpec(1080, 1920, "tiktok vertical 9:16"),
    ("tiktok", "reel"): ImageSpec(1080, 1920, "tiktok vertical 9:16"),
}

_DEFAULT = ImageSpec(1080, 1350, "default portrait 4:5")
_DEFAULT_REEL = ImageSpec(1080, 1920, "default reel 9:16")

# 1:1 es el único encuadre que ninguna red recorta de forma agresiva (IG/FB/LinkedIn/X feed,
# y centrado sobre lienzo vertical en TikTok): por eso el formato universal es cuadrado.
_UNIVERSAL = ImageSpec(1080, 1080, "universal 1:1 (multi-red)")

CONTENT_FORMATS = ("feed", "story", "reel", "user_clip_reel", "universal")
VIDEO_FORMATS = ("reel", "user_clip_reel")

# Formatos ofrecidos por red. TikTok no tiene post de feed horizontal y LinkedIn nativo
# (solo imagen, perfil personal) no publica historias ni reels desde este pipeline.
_NETWORK_FORMATS: dict[str, tuple[str, ...]] = {
    "instagram": ("feed", "story", "reel", "user_clip_reel", "universal"),
    "ig": ("feed", "story", "reel", "user_clip_reel", "universal"),
    "facebook": ("feed", "story", "reel", "user_clip_reel", "universal"),
    "fb": ("feed", "story", "reel", "user_clip_reel", "universal"),
    "linkedin": ("feed", "universal"),
    "tiktok": ("story", "reel", "user_clip_reel", "universal"),
    "x": ("feed", "reel", "universal"),
    "twitter": ("feed", "reel", "universal"),
}

_FORMAT_LABELS: dict[str, str] = {
    "feed": "Post en feed",
    "story": "Historia (vertical)",
    "reel": "Reel — video generado con IA",
    "user_clip_reel": "Video con mis clips (Drive)",
    "universal": "Universal — encaja en todas las redes",
}

NETWORKS: tuple[tuple[str, str], ...] = (
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("linkedin", "LinkedIn"),
    ("tiktok", "TikTok"),
    ("x", "X (Twitter)"),
)


def resolve_image_spec(red_social: str, content_format: str = "feed") -> ImageSpec:
    """Resuelve width×height según plataforma y tipo feed/story/reel/user_clip_reel/universal."""
    platform = (red_social or "instagram").strip().lower()
    fmt = (content_format or "feed").strip().lower()
    if fmt not in CONTENT_FORMATS:
        fmt = "feed"
    # El universal es idéntico en todas las redes: ese es justamente su contrato.
    if fmt == "universal":
        return _UNIVERSAL
    # user_clip_reel no tiene entradas por plataforma en _SPECS: siempre resuelve al default 9:16 del reel.
    if fmt == "user_clip_reel":
        return _DEFAULT_REEL
    default = _DEFAULT_REEL if fmt == "reel" else _DEFAULT
    return _SPECS.get((platform, fmt), default)


def formats_for_network(red_social: str) -> list[dict]:
    """Formatos disponibles para una red, con sus dimensiones resueltas (para el selector del dashboard)."""
    platform = (red_social or "instagram").strip().lower()
    ids = _NETWORK_FORMATS.get(platform, CONTENT_FORMATS)
    options: list[dict] = []
    for fmt in ids:
        spec = resolve_image_spec(platform, fmt)
        options.append(
            {
                "id": fmt,
                "label": _FORMAT_LABELS[fmt],
                "width": spec.width,
                "height": spec.height,
                "is_video": fmt in VIDEO_FORMATS,
            }
        )
    return options


def fal_image_size_arg(spec: ImageSpec) -> dict[str, int] | str:
    """Argumento `image_size` para fal.ai Flux (objeto width/height, múltiplos de 8)."""
    w, h = spec.width, spec.height
    max_dim = 1440
    if w > max_dim or h > max_dim:
        scale = min(max_dim / w, max_dim / h)
        w = int(w * scale)
        h = int(h * scale)
    w = max(512, (w // 8) * 8)
    h = max(512, (h // 8) * 8)
    return {"width": w, "height": h}
