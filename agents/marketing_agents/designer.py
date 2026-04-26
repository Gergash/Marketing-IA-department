from .image_providers import generate_image
from .schemas import BriefInput, CopyOutput, DesignOutput


class DesignerAgent:
    def run(self, brief: BriefInput, copy: CopyOutput) -> DesignOutput:
        prompt = (
            f"Professional social media image for {brief.red_social}. "
            f"Topic: {brief.tema}. "
            f"Target audience: {brief.publico_objetivo}. "
            f"Brand tone: {brief.tono_marca}. "
            f"Style: modern, clean, corporate. No text overlay. High quality."
        )
        return DesignOutput(image_url=generate_image(prompt), image_prompt=prompt)
