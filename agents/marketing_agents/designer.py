"""Agente diseñador: arquetipos editoriales + Flux + composición post-generación."""

from .image_providers import generate_image
from .image_specs import resolve_image_spec
from .layout_archetypes import build_flux_prompt, pick_archetype
from .schemas import BriefInput, CopyOutput, DesignOutput, StrategyOutput


class DesignerAgent:
    """Genera piezas visuales tipo agencia: arquetipo + prompt Flux + overlay editorial."""

    def run(
        self,
        brief: BriefInput,
        copy: CopyOutput,
        strategy: StrategyOutput,
        *,
        image_provider: str | None = None,
        content_format: str = "feed",
    ) -> DesignOutput:
        """Selecciona layout, genera imagen dimensionada y aplica composición tipográfica."""
        from gateway.app.core.settings import get_settings

        spec = resolve_image_spec(brief.red_social, content_format)
        archetype = pick_archetype(brief, strategy)
        prompt = build_flux_prompt(archetype, brief=brief, strategy=strategy, spec=spec)

        used_provider = (image_provider or get_settings().image_provider).strip().lower()
        headline = copy.headline_for_image.strip() or strategy.hook or copy.copy_final[:100]
        subline = copy.subline_for_image.strip() or None

        url, width, height = generate_image(
            prompt,
            overlay_text=headline,
            overlay_subline=subline,
            overlay_cta=copy.cta,
            image_provider=used_provider,
            red_social=brief.red_social,
            content_format=content_format,
            layout_archetype=archetype.id,
        )
        palette = f"primary={archetype.primary_hex}, accent={archetype.accent_hex}"
        return DesignOutput(
            image_url=url,
            image_prompt=prompt,
            image_provider=used_provider,
            image_width=width,
            image_height=height,
            content_format=content_format,
            layout_archetype=archetype.id,
            layout_label=archetype.label,
            color_palette=palette,
        )
