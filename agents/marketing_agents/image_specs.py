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


# Instagram: feed cuadrado 1:1 (1080×1080); story/reels 9:16 (1080×1920)
# LinkedIn: feed recomendado 1200×627; documentado también 1080×1080
# Facebook: feed 1080×1080 o enlace 1200×630
_SPECS: dict[tuple[str, str], ImageSpec] = {
    ("instagram", "feed"): ImageSpec(1080, 1080, "instagram feed 1:1"),
    ("instagram", "story"): ImageSpec(1080, 1920, "instagram story 9:16"),
    ("ig", "feed"): ImageSpec(1080, 1080, "instagram feed 1:1"),
    ("ig", "story"): ImageSpec(1080, 1920, "instagram story 9:16"),
    ("facebook", "feed"): ImageSpec(1080, 1080, "facebook feed 1:1"),
    ("facebook", "story"): ImageSpec(1080, 1920, "facebook story 9:16"),
    ("fb", "feed"): ImageSpec(1080, 1080, "facebook feed 1:1"),
    ("linkedin", "feed"): ImageSpec(1200, 627, "linkedin feed 1.91:1"),
    ("linkedin", "story"): ImageSpec(1080, 1920, "linkedin story 9:16"),
    ("x", "feed"): ImageSpec(1200, 675, "x feed 16:9"),
    ("twitter", "feed"): ImageSpec(1200, 675, "x feed 16:9"),
    ("tiktok", "feed"): ImageSpec(1080, 1920, "tiktok vertical 9:16"),
    ("tiktok", "story"): ImageSpec(1080, 1920, "tiktok vertical 9:16"),
}

_DEFAULT = ImageSpec(1080, 1080, "default square 1:1")


def resolve_image_spec(red_social: str, content_format: str = "feed") -> ImageSpec:
    """Resuelve width×height según plataforma y tipo feed/story."""
    platform = (red_social or "instagram").strip().lower()
    fmt = (content_format or "feed").strip().lower()
    if fmt not in ("feed", "story"):
        fmt = "feed"
    return _SPECS.get((platform, fmt), _DEFAULT)


def fal_image_size_arg(spec: ImageSpec) -> dict[str, int] | str:
    """Argumento `image_size` para fal.ai Flux (objeto width/height, múltiplos de 8)."""
    w = max(512, min(1440, spec.width))
    h = max(512, min(1440, spec.height))
    w = (w // 8) * 8
    h = (h // 8) * 8
    return {"width": w, "height": h}
