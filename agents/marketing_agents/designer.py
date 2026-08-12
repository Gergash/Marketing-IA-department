"""Agente diseñador: arquetipos editoriales + Flux + composición post-generación."""

from .brand_visual import (
    apply_brand_to_archetype,
    brand_priority_prompt_block,
    extract_brand_name_candidates,
    resolve_brand_cues,
    resolve_brand_font_paths,
)
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
        cta_on_image: bool = False,
        tenant_id: str | None = None,
    ) -> DesignOutput:
        """Selecciona layout, genera imagen dimensionada y aplica composición tipográfica."""
        from gateway.app.core.settings import get_settings

        spec = resolve_image_spec(brief.red_social, content_format)
        archetype = (
            get_archetype(archetype_override) or pick_archetype(brief, strategy)
            if archetype_override
            else pick_archetype(brief, strategy)
        )

        brand_text = (getattr(brief, "brand_context", "") or "").strip()
        assets = {
            "palette_hex": list(getattr(brief, "brand_palette", None) or []),
            "logo_urls": list(getattr(brief, "brand_logo_urls", None) or []),
            "logo_paths": list(getattr(brief, "brand_logo_paths", None) or []),
        }
        tid = tenant_id or getattr(brief, "tenant_id", None) or None
        cues = resolve_brand_cues(
            brand_text,
            tenant_id=tid,
            assets=assets if any(assets.values()) else None,
        )
        # Con señales de marca: preferir arquetipo detectado en el manual; si no, campaña
        if cues.has_signal and not archetype_override:
            suggested = get_archetype(cues.suggested_archetype) if cues.suggested_archetype else None
            archetype = suggested or get_archetype("brand_campaign_piece") or archetype
        archetype = apply_brand_to_archetype(archetype, cues)
        font_paths = resolve_brand_font_paths(cues.font_names, brand_text)
        brand_block = brand_priority_prompt_block(cues, brand_text)
        logo_path = (cues.logo_paths[0] if getattr(cues, "logo_paths", None) else None) or None
        brand_names = extract_brand_name_candidates(brand_text, brief.tema)

        prompt = build_flux_prompt(
            archetype,
            brief=brief,
            strategy=strategy,
            spec=spec,
            brand_block=brand_block,
        )

        notes = (revision_notes or "").strip()
        if notes:
            # Las correcciones del humano pesan más que el prompt base: van al final para
            # que el modelo las lea como ajuste sobre lo ya descrito.
            prompt = f"{prompt}\n\nRevision requested by the human reviewer: {notes}"
            visual_instructions = f"{visual_instructions}. {notes}" if visual_instructions else notes

        used_provider = (image_provider or get_settings().image_provider).strip().lower()
        headline = copy.headline_for_image.strip() or strategy.hook or copy.copy_final[:100]
        subline = copy.subline_for_image.strip() or None
        # CTA en imagen: on-demand, o siempre en pieza de campaña con marca.
        want_cta = cta_on_image or archetype.id == "brand_campaign_piece"
        overlay_cta = copy.cta if want_cta and (copy.cta or "").strip() else None
        # Eslogan corto: primera línea del copy si no es el headline
        tagline = None
        if archetype.id == "brand_campaign_piece":
            body = (copy.copy_final or "").strip().split("\n")[0].strip()
            if body and body.lower() not in (headline or "").lower() and len(body) <= 90:
                tagline = body

        overlay_kwargs = dict(
            brand_archetype=archetype,
            preferred_font_paths=font_paths or None,
            logo_path=logo_path,
            tagline=tagline,
            brand_names=brand_names or None,
            font_seed=f"{archetype.id}:{brief.red_social}:{brief.tema}",
        )

        if user_asset_url and user_asset_url.strip():
            url, width, height, design_source = compose_from_user_asset(
                user_asset_url.strip(),
                spec=spec,
                overlay_text=headline,
                overlay_subline=subline,
                overlay_cta=overlay_cta,
                red_social=brief.red_social,
                layout_archetype=archetype.id,
                content_format=content_format,
                alter_with_ai=alter_image_with_ai,
                visual_instructions=visual_instructions,
                image_provider=used_provider,
                **overlay_kwargs,
            )
            img_prompt = visual_instructions or prompt if alter_image_with_ai else f"user_asset:{user_asset_url}"
            provider_label = "fal_img2img" if design_source == "user_img2img" else "user_overlay"
        else:
            url, width, height = generate_image(
                prompt,
                overlay_text=headline,
                overlay_subline=subline,
                overlay_cta=overlay_cta,
                image_provider=used_provider,
                red_social=brief.red_social,
                content_format=content_format,
                layout_archetype=archetype.id,
                **overlay_kwargs,
            )
            img_prompt = prompt
            provider_label = used_provider
            design_source = "generated"

        palette_bits = (cues.palette_hex or [])[:5]
        if palette_bits:
            palette = ", ".join(palette_bits) + " (from brand manual scan)"
        else:
            palette = f"primary={archetype.primary_hex}, accent={archetype.accent_hex}"
            if cues.has_signal:
                palette += " (from brand manual)"
        if cues.logo_paths:
            palette += f"; logos={len(cues.logo_paths)}"
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
