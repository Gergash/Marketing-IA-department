"""Arquetipos de layout editorial para posts de redes (referencia: Mattelsa, RADAR, YaComercio)."""

from __future__ import annotations

from dataclasses import dataclass

from .image_specs import ImageSpec
from .schemas import BriefInput, CopyOutput, StrategyOutput

# IDs estables usados en prompts, overlay y API
ARCHETYPES = (
    "typographic_poster",
    "minimal_conceptual",
    "editorial_infographic",
    "cinematic_hero",
)


@dataclass(frozen=True)
class LayoutArchetype:
    """Definición de un arquetipo visual: estilo Flux + composición de overlay."""

    id: str
    label: str
    flux_style: str
    flux_composition: str
    primary_hex: str
    secondary_hex: str
    accent_hex: str


_ARCHETYPE_MAP: dict[str, LayoutArchetype] = {
    "typographic_poster": LayoutArchetype(
        id="typographic_poster",
        label="Poster tipográfico",
        flux_style=(
            "bold editorial social media poster, high contrast, film grain texture optional, "
            "minimal background, dramatic lighting, magazine quality"
        ),
        flux_composition=(
            "large negative space in lower 40% for typography overlay, subject or abstract "
            "visual in upper area, asymmetric layout"
        ),
        primary_hex="#FFE500",
        secondary_hex="#FFFFFF",
        accent_hex="#FFE500",
    ),
    "minimal_conceptual": LayoutArchetype(
        id="minimal_conceptual",
        label="Conceptual minimal",
        flux_style=(
            "clean minimal conceptual advertising, soft studio lighting, warm off-white atmosphere, "
            "single strong visual metaphor, premium brand aesthetic"
        ),
        flux_composition=(
            "centered or rule-of-thirds hero object, generous whitespace at top for headline, "
            "uncluttered background"
        ),
        primary_hex="#1A1A1A",
        secondary_hex="#5A5A5A",
        accent_hex="#7CB518",
    ),
    "editorial_infographic": LayoutArchetype(
        id="editorial_infographic",
        label="Infográfico editorial",
        flux_style=(
            "modern editorial infographic background, high contrast black white and lime accent, "
            "professional marketing, icons and shapes subtle in background"
        ),
        flux_composition=(
            "central visual anchor, structured layout zones, space for headline blocks and icons, "
            "clean corporate PowerUps style"
        ),
        primary_hex="#111111",
        secondary_hex="#FFFFFF",
        accent_hex="#A2D729",
    ),
    "cinematic_hero": LayoutArchetype(
        id="cinematic_hero",
        label="Hero cinematográfico",
        flux_style=(
            "cinematic moody photography, shallow depth of field, spotlight, dark green or navy tones, "
            "professional campaign quality"
        ),
        flux_composition=(
            "hero subject in center, bottom third darker for text overlay, atmospheric depth, "
            "no clutter"
        ),
        primary_hex="#FFFFFF",
        secondary_hex="#E5E7EB",
        accent_hex="#9333EA",
    ),
}


def pick_archetype(brief: BriefInput, strategy: StrategyOutput) -> LayoutArchetype:
    """Elige arquetipo según tipo de post, objetivo y plataforma."""
    tipo = (strategy.tipo_post or "").lower()
    objetivo = (brief.objetivo or "").lower()
    tema = (brief.tema or "").lower()

    if tipo == "educativo" or "branding" in objetivo or "automatiz" in tema:
        return _ARCHETYPE_MAP["editorial_infographic"]
    if tipo == "promocional" or "ventas" in objetivo:
        return _ARCHETYPE_MAP["typographic_poster"]
    if tipo == "informativo":
        return _ARCHETYPE_MAP["minimal_conceptual"]
    if tipo in ("entretenimiento", "storytelling"):
        return _ARCHETYPE_MAP["cinematic_hero"]
    return _ARCHETYPE_MAP["typographic_poster"]


def build_flux_prompt(
    archetype: LayoutArchetype,
    *,
    brief: BriefInput,
    strategy: StrategyOutput,
    spec: ImageSpec,
) -> str:
    """Prompt visual enriquecido para Flux — fondo sin texto, composición editorial."""
    metaphor = _visual_metaphor_hint(brief, strategy)
    return (
        f"Social media {spec.label} design background for {brief.red_social}. "
        f"Topic: {brief.tema}. Audience: {brief.publico_objetivo}. "
        f"Brand tone: {brief.tono_marca}. Post type: {strategy.tipo_post}. "
        f"Visual metaphor: {metaphor}. "
        f"Style: {archetype.flux_style}. "
        f"Composition: {archetype.flux_composition}. "
        f"Color direction: accent {archetype.accent_hex}, high-end agency quality. "
        "Absolutely no text, no letters, no logos, no watermark in the generated image."
    )


def _visual_metaphor_hint(brief: BriefInput, strategy: StrategyOutput) -> str:
    """Metáfora visual corta derivada del brief (sin LLM extra)."""
    tema = brief.tema.lower()
    if "instagram" in tema or "redes" in tema or "social" in tema:
        return "breaking dependency on single platform, digital independence"
    if "ia" in tema or "inteligencia" in tema or "automatiz" in tema:
        return "human plus AI collaboration, futuristic workflow"
    if "dato" in tema or "decision" in tema:
        return "data-driven clarity, precision and insight"
    if strategy.tipo_post == "promocional":
        return "growth, momentum, bold transformation"
    return f"professional {brief.objetivo} for {brief.publico_objetivo}"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convierte #RRGGBB a tupla RGB."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
