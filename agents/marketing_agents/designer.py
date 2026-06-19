"""Agente diseñador: construye prompt visual y obtiene URL de imagen."""

from .image_providers import generate_image
from .image_specs import resolve_image_spec
from .schemas import BriefInput, CopyOutput, DesignOutput


class DesignerAgent:
    """Construye el prompt visual y obtiene la URL de imagen (fal.ai, SD, DALL·E, etc.)."""

    def run(
        self,
        brief: BriefInput,
        copy: CopyOutput,
        *,
        image_provider: str | None = None,
        content_format: str = "feed",
    ) -> DesignOutput:
        """Genera imagen dimensionada por plataforma/formato con overlay headline + CTA."""
        from gateway.app.core.settings import get_settings

        spec = resolve_image_spec(brief.red_social, content_format)
        prompt = (
            f"Professional social media marketing background for {brief.red_social} {content_format}. "
            f"Topic: {brief.tema}. "
            f"Target audience: {brief.publico_objetivo}. "
            f"Brand tone: {brief.tono_marca}. "
            f"Style: modern, clean, corporate, photorealistic. "
            f"Aspect ratio {spec.label}. No text in image."
        )
        used_provider = (image_provider or get_settings().image_provider).strip().lower()
        headline = copy.headline_for_image.strip() or copy.copy_final[:100]
        subline = copy.subline_for_image.strip() or None
        url, width, height = generate_image(
            prompt,
            overlay_text=headline,
            overlay_subline=subline,
            overlay_cta=copy.cta,
            image_provider=used_provider,
            red_social=brief.red_social,
            content_format=content_format,
        )
        return DesignOutput(
            image_url=url,
            image_prompt=prompt,
            image_provider=used_provider,
            image_width=width,
            image_height=height,
            content_format=content_format,
        )
