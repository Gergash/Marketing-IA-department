"""Arquetipos de layout editorial para posts de redes.

Referencias: pieza de campaña con manual de marca (Tres Amores / full-bleed),
Mattelsa, RADAR, YaComercio.
"""

from __future__ import annotations

from dataclasses import dataclass

from .image_specs import ImageSpec
from .schemas import BriefInput, StrategyOutput

# IDs estables usados en prompts, overlay y API
ARCHETYPES = (
    "brand_campaign_piece",
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
    # Pieza canónica con manual de marca (ref: docs/references/brand-campaign-piece-tres-amores.png)
    "brand_campaign_piece": LayoutArchetype(
        id="brand_campaign_piece",
        label="Campaña con marca",
        flux_style=(
            "premium full-bleed product photography for social campaign, shallow depth of field, "
            "warm atmospheric bokeh, real product or place as the dominant visual plane, "
            "upscale restaurant/retail/hospitality advertising quality, no graphic templates"
        ),
        flux_composition=(
            "one edge-to-edge photographic composition: hero product/scene fills the frame, "
            "soft vignette, leave clear top-center band for logo mark, mid-upper zone for "
            "headline overlay, lower third quieter for CTA — no cards, no collages, no inset panels"
        ),
        primary_hex="#FFFFFF",
        secondary_hex="#F5E6C8",
        accent_hex="#C9A227",
    ),
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
        primary_hex="#F8FAFC",
        secondary_hex="#E2E8F0",
        accent_hex="#0F766E",
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


def get_archetype(archetype_id: str) -> LayoutArchetype | None:
    """Devuelve el arquetipo por ID, o None si no existe."""
    return _ARCHETYPE_MAP.get(archetype_id)


def pick_archetype(brief: BriefInput, strategy: StrategyOutput) -> LayoutArchetype:
    """Elige arquetipo. Con manual de marca → pieza de campaña full-bleed (logo/foto/CTA)."""
    tipo = (strategy.tipo_post or "").lower()
    objetivo = (brief.objetivo or "").lower()
    tema = (brief.tema or "").lower()
    brand = (getattr(brief, "brand_context", "") or "").strip()

    # Si hay manual de marca, la pieza objetivo es siempre tipo campaña fotográfica
    # (logo arriba, foto producto edge-to-edge, tipografía centrada, CTA abajo).
    if len(brand) >= 40:
        return _ARCHETYPE_MAP["brand_campaign_piece"]

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
    brand_block: str = "",
) -> str:
    """Prompt visual enriquecido — brand manual primero si existe."""
    metaphor = _visual_metaphor_hint(brief, strategy)
    cues_has = False
    try:
        from .brand_visual import parse_brand_visual_cues

        cues_has = parse_brand_visual_cues(getattr(brief, "brand_context", "") or "").has_signal
    except Exception:
        cues_has = False
    priority = brand_block
    if not priority:
        from .brand_visual import brand_priority_prompt_block, parse_brand_visual_cues

        cues = parse_brand_visual_cues(getattr(brief, "brand_context", "") or "")
        cues_has = cues.has_signal
        priority = brand_priority_prompt_block(cues, getattr(brief, "brand_context", "") or "")
    base = (
        f"Social media {spec.label} design background for {brief.red_social}. "
        f"Topic: {brief.tema}. Audience: {brief.publico_objetivo}. "
        f"Brand tone: {brief.tono_marca}. Post type: {strategy.tipo_post}. "
        f"Visual metaphor: {metaphor}. "
        f"Style: {archetype.flux_style}. "
        f"Composition: {archetype.flux_composition}. "
        f"Color direction: primary {archetype.primary_hex}, accent {archetype.accent_hex}, "
        f"high-end agency quality tailored to this client. "
        "Absolutely no text, no letters, no logos, no watermark in the generated image."
    )
    if priority:
        if archetype.id == "brand_campaign_piece":
            return (
                f"{priority} {base} Composition must match a brand-manual campaign piece: "
                "full-bleed real photography of the client's product/place/atmosphere, "
                "logo reserved at top-center, centered expressive headline, short supporting line, "
                "single CTA near the bottom — no cards, no dashboards, no collages."
            )
        return f"{priority} {base}"
    # Sin manual: evitar el look genérico amarillo/blanco como default implícito
    if archetype.id == "typographic_poster" and not cues_has:
        return (
            f"{base} Prefer rich, distinctive photography or illustration — "
            "avoid generic yellow-and-white template aesthetics."
        )
    return base


def _visual_metaphor_hint(brief: BriefInput, strategy: StrategyOutput) -> str:
    """Metáfora visual corta derivada del brief (sin LLM extra).

    El orden importa: keywords específicos (IoT, cámaras) van antes que coincidencias
    amplias como \"ia\" dentro de \"con IA\", que de otro modo diluyen el tema.
    """
    tema = brief.tema.lower()
    if any(k in tema for k in ("iot", "cámara", "camara", "seguridad", "vigilancia", "cctv")):
        return (
            "smart city IoT security cameras, AI video analytics dashboard, "
            "surveillance sensors connected to a control center"
        )
    if "instagram" in tema or "redes" in tema or "social" in tema:
        return "breaking dependency on single platform, digital independence"
    if "inteligencia artificial" in tema or "automatiz" in tema or tema.endswith(" ia") or " ia " in f" {tema} ":
        return "human plus AI collaboration, futuristic workflow"
    if "dato" in tema or "decision" in tema:
        return "data-driven clarity, precision and insight"
    if strategy.tipo_post == "promocional":
        return "growth, momentum, bold transformation"
    return f"professional scene about {brief.tema} for {brief.publico_objetivo}, {brief.objetivo}"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convierte #RRGGBB a tupla RGB."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
