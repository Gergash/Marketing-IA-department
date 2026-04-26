import structlog

from .llm import get_llm
from .schemas import BriefInput, StrategyOutput

logger = structlog.get_logger(__name__)

_SYSTEM = """\
You are an expert social media content strategist.
Given a marketing brief, produce a focused, platform-aware content strategy.

Return ONLY valid JSON with exactly these fields:
{
  "tipo_post": "<one of: educativo | promocional | entretenimiento | informativo>",
  "hook":       "<attention-grabbing opening line, max 120 chars>",
  "mensaje_base": "<core message, 2-3 sentences>",
  "hashtags":   ["<3-5 relevant hashtags with # prefix>"]
}

Rules:
- Write in the language specified by the 'idioma' field.
- Adapt length and tone to the target platform (LinkedIn: professional long-form; Instagram: punchy; X/Twitter: ultra-short).
- Never include emojis unless the tone explicitly calls for them.\
"""


class ContentStrategistAgent:
    def run(self, brief: BriefInput) -> StrategyOutput:
        llm = get_llm()
        if llm is None:
            logger.warning("strategist.using_stub", reason="no_llm_configured")
            return self._stub(brief)
        prompt = (
            f"- Topic (tema): {brief.tema}\n"
            f"- Target audience: {brief.publico_objetivo}\n"
            f"- Platform: {brief.red_social}\n"
            f"- Goal: {brief.objetivo}\n"
            f"- Brand tone: {brief.tono_marca}\n"
            f"- Language: {brief.idioma}"
        )
        try:
            data = llm.complete_json(_SYSTEM, prompt)
            return StrategyOutput(**data)
        except Exception as exc:
            logger.error("strategist.llm_error", error=str(exc))
            return self._stub(brief)

    def _stub(self, brief: BriefInput) -> StrategyOutput:
        return StrategyOutput(
            tipo_post="educativo",
            hook=f"¿Sabias que {brief.tema.lower()} puede acelerar tus resultados?",
            mensaje_base=(
                f"Contenido {brief.objetivo} para {brief.publico_objetivo} en "
                f"{brief.red_social} con enfoque {brief.tono_marca}."
            ),
            hashtags=["#IA", "#MarketingDigital", "#Automatizacion"],
        )
