"""Agente diseñador: arquetipos editoriales + Flux + composición post-generación."""

from dataclasses import replace

import structlog

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
from .overlay_text import font_paths_for_typography
from .revision_prompt import (
    compose_visual_prompt,
    parse_typography_revision,
    revision_requests_people,
    revision_requests_scene_change,
    scene_revision_notes,
)
from .schemas import BriefInput, CopyOutput, DesignOutput, StrategyOutput
from .visual_prompt_guards import with_photo_only_guard

logger = structlog.get_logger(__name__)


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
        typo = parse_typography_revision(notes)
        want_people = revision_requests_people(notes)
        want_scene = revision_requests_scene_change(notes)
        if want_people:
            prompt = with_photo_only_guard(prompt, allow_people=True)

        used_provider = (image_provider or get_settings().image_provider).strip().lower()
        model_for_budget = (
            get_settings().venice_image_model
            if used_provider == "venice"
            else "gpt-image-2"
        )
        # Guardar indicaciones de escena del usuario ANTES de mezclar notas de revisión
        # (tipografía va a Pillow; escena va a revision_notes del editor).
        scene_user_instructions = (visual_instructions or "").strip() or None
        if notes and want_scene:
            prompt = compose_visual_prompt(
                prompt,
                model=model_for_budget,
                revision_notes=notes,
            )
            visual_instructions = (
                f"{scene_user_instructions}. {notes}" if scene_user_instructions else notes
            )
        elif notes and typo.requested:
            # Solo tipografía: no contaminar el prompt generativo.
            visual_instructions = scene_user_instructions

        if notes:
            logger.info(
                "designer.revision_applied",
                people=want_people,
                scene_change=want_scene,
                typography=typo.requested,
                typo_style=typo.style,
                typo_family=typo.family_id,
                notes_preview=notes[:120],
            )

        # Aplicar tipografía HITL al overlay Pillow (familia, color, tamaño).
        font_seed = f"{archetype.id}:{brief.red_social}:{brief.tema}"
        overlay_typo: dict = {
            "title_size_scale": 1.0,
            "force_text_hex": None,
            "high_contrast": False,
            "typography_style": None,
            "typography_family_id": None,
            "force_uppercase": None,
        }
        if typo.requested:
            font_seed = f"{font_seed}:typo:{typo.style or ''}:{typo.family_id or notes[:48]}"
            typo_paths = font_paths_for_typography(
                style=typo.style,
                family_id=typo.family_id,
                font_seed=font_seed,
            )
            if typo_paths:
                font_paths = typo_paths
            if typo.text_color_hex:
                archetype = replace(
                    archetype,
                    primary_hex=typo.text_color_hex,
                    secondary_hex=typo.text_color_hex,
                )
            overlay_typo = {
                "title_size_scale": typo.size_scale,
                "force_text_hex": typo.text_color_hex,
                "high_contrast": typo.high_contrast,
                "typography_style": typo.style,
                "typography_family_id": typo.family_id,
                "force_uppercase": typo.force_uppercase,
            }

        headline = copy.headline_for_image.strip() or strategy.hook or copy.copy_final[:100]
        subline = copy.subline_for_image.strip() or None
        want_cta = cta_on_image or archetype.id == "brand_campaign_piece"
        overlay_cta = copy.cta if want_cta and (copy.cta or "").strip() else None
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
            font_seed=font_seed,
            **overlay_typo,
        )

        # Foto real + notas que piden cambiar la ESCENA (p.ej. agregar personas):
        # hay que editar la foto con IA. Tipografía sola NUNCA auto-activa el edit.
        use_user_asset = bool(user_asset_url and user_asset_url.strip())
        effective_alter = bool(alter_image_with_ai)
        if use_user_asset and notes and want_scene and not effective_alter:
            logger.info(
                "designer.auto_enable_image_edit",
                reason=(
                    "Notas de revisión piden cambiar la escena sobre foto real; "
                    "se activa edición IA (Venice gpt-image-2-edit / fal FLUX Kontext)."
                ),
            )
            effective_alter = True
        if use_user_asset and notes and typo.requested and not want_scene and effective_alter:
            # Si el run original tenía alter ON pero la revisión es solo tipografía,
            # no re-editar la escena (evita personas default / deformaciones).
            logger.info(
                "designer.skip_image_edit_for_typography_only",
                reason="Revisión solo tipográfica: se recompone overlay Pillow sin re-editar la foto.",
            )
            effective_alter = False

        if use_user_asset:
            # Instrucciones de escena puras. Tipografía NO se manda al editor IA.
            scene_instructions = scene_user_instructions
            scene_notes = scene_revision_notes(notes)
            if effective_alter and not scene_instructions and not scene_notes:
                scene_instructions = (
                    "Agrega dos personas realistas sentadas en las sillas vacías de la mesa"
                )
            url, width, height, design_source = compose_from_user_asset(
                user_asset_url.strip(),
                spec=spec,
                overlay_text=headline,
                overlay_subline=subline,
                overlay_cta=overlay_cta,
                red_social=brief.red_social,
                layout_archetype=archetype.id,
                content_format=content_format,
                alter_with_ai=effective_alter,
                visual_instructions=scene_instructions,
                revision_notes=scene_notes,
                image_provider=used_provider,
                **overlay_kwargs,
            )
            img_prompt = (
                visual_instructions or prompt if effective_alter else f"user_asset:{user_asset_url}"
            )
            if typo.requested:
                img_prompt = f"{img_prompt} | typography_revision={notes[:160]}"
            provider_label = (
                f"{used_provider}_edit" if design_source == "user_img2img" else "user_overlay"
            )
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
            if typo.requested:
                img_prompt = f"{img_prompt} | typography_revision={notes[:160]}"
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
        if typo.requested:
            palette += f"; typography_revision={typo.style or typo.family_id or 'custom'}"
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
