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
    ("twitter", "feed"): ImageSpec(1200, 675, "x feed 16:9"),
    ("tiktok", "feed"): ImageSpec(1080, 1920, "tiktok vertical 9:16"),
    ("tiktok", "story"): ImageSpec(1080, 1920, "tiktok vertical 9:16"),
}

_DEFAULT = ImageSpec(1080, 1350, "default portrait 4:5")
_DEFAULT_REEL = ImageSpec(1080, 1920, "default reel 9:16")


def resolve_image_spec(red_social: str, content_format: str = "feed") -> ImageSpec:
    """Resuelve width×height según plataforma y tipo feed/story/reel/user_clip_reel."""
    platform = (red_social or "instagram").strip().lower()
    fmt = (content_format or "feed").strip().lower()
    if fmt not in ("feed", "story", "reel", "user_clip_reel"):
        fmt = "feed"
    # user_clip_reel no tiene entradas por plataforma en _SPECS: siempre resuelve al default 9:16 del reel.
    if fmt == "user_clip_reel":
        return _DEFAULT_REEL
    default = _DEFAULT_REEL if fmt == "reel" else _DEFAULT
    return _SPECS.get((platform, fmt), default)


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
