"""Agente diseñador: construye prompt visual y obtiene URL de imagen."""

from .image_providers import generate_image
from .schemas import BriefInput, CopyOutput, DesignOutput


class DesignerAgent:
    """Construye el prompt visual y obtiene la URL de imagen (fal.ai, SD, DALL·E, etc.)."""

    def run(self, brief: BriefInput, copy: CopyOutput) -> DesignOutput:
        """Genera imagen con texto superpuesto (copy + CTA) cuando el proveedor lo soporta."""
        prompt = (
            f"Professional social media marketing background for {brief.red_social}. "
            f"Topic: {brief.tema}. "
            f"Target audience: {brief.publico_objetivo}. "
            f"Brand tone: {brief.tono_marca}. "
            f"Style: modern, clean, corporate, photorealistic. High quality."
        )
        url = generate_image(
            prompt,
            overlay_text=copy.copy_final,
            overlay_cta=copy.cta,
        )
        return DesignOutput(image_url=url, image_prompt=prompt)
