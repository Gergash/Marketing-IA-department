from .schemas import CopyOutput, StrategyOutput


class CopywriterAgent:
    def run(self, strategy: StrategyOutput) -> CopyOutput:
        copy_text = (
            f"{strategy.hook}\n\n"
            f"{strategy.mensaje_base}\n"
            "Con un flujo de agentes puedes pasar de idea a post en minutos."
        )
        cta = "Escribe 'MVP' y te compartimos una demo del flujo."
        hashtags = strategy.hashtags + ["#Growth", "#SocialMedia"]
        return CopyOutput(copy_final=copy_text, hashtags=hashtags, cta=cta)
