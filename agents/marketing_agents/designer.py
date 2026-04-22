from .schemas import BriefInput, CopyOutput, DesignOutput


class DesignerAgent:
    def run(self, brief: BriefInput, copy: CopyOutput) -> DesignOutput:
        prompt = (
            f"Create social media image for {brief.red_social} about {brief.tema}. "
            f"Tone: {brief.tono_marca}. Include CTA: {copy.cta}"
        )
        # Placeholder output; later this can call OpenAI Images/Canva.
        image_url = f"https://dummyimage.com/1200x630/1a202c/ffffff&text={brief.tema.replace(' ', '+')}"
        return DesignOutput(image_url=image_url, image_prompt=prompt)
