"""Agente diseñador: construye prompt visual y obtiene URL de imagen."""

from .image_providers import generate_image
from .schemas import BriefInput, CopyOutput, DesignOutput


class DesignerAgent:
    """Construye el prompt visual y obtiene la URL de imagen (fal.ai, SD, DALL·E, etc.)."""

    def run(
        self,
        brief: BriefInput,
        copy: CopyOutput,
        *,
        image_provider: str | None = None,
    ) -> DesignOutput:
        """Genera imagen con texto superpuesto (copy + CTA) cuando el proveedor lo soporta."""
        from gateway.app.core.settings import get_settings

        prompt = (
            f"Professional social media marketing background for {brief.red_social}. "
            f"Topic: {brief.tema}. "
            f"Target audience: {brief.publico_objetivo}. "
            f"Brand tone: {brief.tono_marca}. "
            f"Style: modern, clean, corporate, photorealistic. High quality."
        )
        used_provider = (image_provider or get_settings().image_provider).strip().lower()
        url = generate_image(
            prompt,
            overlay_text=copy.copy_final,
            overlay_cta=copy.cta,
            image_provider=used_provider,
        )
        return DesignOutput(
            image_url=url,
            image_prompt=prompt,
            image_provider=used_provider,
        )
