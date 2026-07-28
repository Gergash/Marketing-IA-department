"""Agente diseñador: arquetipos editoriales + Flux + composición post-generación."""

from .image_providers import compose_from_user_asset, generate_image
from .image_specs import resolve_image_spec
from .layout_archetypes import build_flux_prompt, get_archetype, pick_archetype
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
        archetype_override: str | None = None,
        user_asset_url: str | None = None,
        alter_image_with_ai: bool = False,
        visual_instructions: str | None = None,
        revision_notes: str | None = None,
    ) -> DesignOutput:
        """Selecciona layout, genera imagen dimensionada y aplica composición tipográfica."""
        from gateway.app.core.settings import get_settings

        spec = resolve_image_spec(brief.red_social, content_format)
        archetype = (
            get_archetype(archetype_override) or pick_archetype(brief, strategy)
            if archetype_override
            else pick_archetype(brief, strategy)
        )
        prompt = build_flux_prompt(archetype, brief=brief, strategy=strategy, spec=spec)

        notes = (revision_notes or "").strip()
        if notes:
            # Las correcciones del humano pesan más que el prompt base: van al final para
            # que el modelo las lea como ajuste sobre lo ya descrito.
            prompt = f"{prompt}\n\nRevision requested by the human reviewer: {notes}"
            visual_instructions = f"{visual_instructions}. {notes}" if visual_instructions else notes

        used_provider = (image_provider or get_settings().image_provider).strip().lower()
        headline = copy.headline_for_image.strip() or strategy.hook or copy.copy_final[:100]
        subline = copy.subline_for_image.strip() or None

        if user_asset_url and user_asset_url.strip():
            url, width, height, design_source = compose_from_user_asset(
                user_asset_url.strip(),
                spec=spec,
                overlay_text=headline,
                overlay_subline=subline,
                overlay_cta=copy.cta,
                red_social=brief.red_social,
                layout_archetype=archetype.id,
                alter_with_ai=alter_image_with_ai,
                visual_instructions=visual_instructions,
                image_provider=used_provider,
            )
            img_prompt = visual_instructions or prompt if alter_image_with_ai else f"user_asset:{user_asset_url}"
            provider_label = "fal_img2img" if design_source == "user_img2img" else "user_overlay"
        else:
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
            img_prompt = prompt
            provider_label = used_provider
            design_source = "generated"

        palette = f"primary={archetype.primary_hex}, accent={archetype.accent_hex}"
        return DesignOutput(
            image_url=url,
            image_prompt=img_prompt,
            image_provider=provider_label,
            image_width=width,
            image_height=height,
            content_format=content_format,
            layout_archetype=archetype.id,
            layout_label=archetype.label,
            color_palette=palette,
            design_source=design_source,
        )
