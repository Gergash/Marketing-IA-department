from .schemas import BriefInput, StrategyOutput


class ContentStrategistAgent:
    def run(self, brief: BriefInput) -> StrategyOutput:
        hook = f"¿Sabias que {brief.tema.lower()} puede acelerar tus resultados?"
        message = (
            f"Contenido {brief.objetivo} para {brief.publico_objetivo} en "
            f"{brief.red_social} con enfoque {brief.tono_marca}."
        )
        hashtags = ["#IA", "#MarketingDigital", "#Automatizacion"]
        return StrategyOutput(
            tipo_post="educativo",
            hook=hook,
            mensaje_base=message,
            hashtags=hashtags,
        )
