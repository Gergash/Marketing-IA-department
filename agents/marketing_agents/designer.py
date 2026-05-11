from .image_providers import generate_image
from .schemas import BriefInput, CopyOutput, DesignOutput


class DesignerAgent:
    def run(self, brief: BriefInput, copy: CopyOutput) -> DesignOutput:
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
