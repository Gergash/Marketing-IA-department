"""Agente estratega: traduce el brief en hook, mensaje y hashtags (LLM o stub)."""

import structlog

from .knowledge import inbound_system_addendum
from .llm import get_llm
from .schemas import BriefInput, StrategyOutput

logger = structlog.get_logger(__name__)

_SYSTEM = """\
You are an expert social media content strategist grounded in inbound marketing.
Given a marketing brief, produce a focused, platform-aware content strategy that
reaches the named community (publico_objetivo) using Attract → Convert → Close → Delight.

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
- Never include emojis unless the tone explicitly calls for them.
- Content intent stack: ENTRETENER → INFORMACION → CONEXION (hook entertains, mensaje informs the segment, strategy implies connection CTA).
""" + inbound_system_addendum(role="strategist")


class ContentStrategistAgent:
    """Define tipo de post, hook, mensaje base y hashtags según el brief (LLM o stub)."""

    def run(self, brief: BriefInput) -> StrategyOutput:
        """Devuelve `StrategyOutput` desde el LLM o `_stub` ante ausencia de LLM o error."""
        llm = get_llm()
        if llm is None:
            logger.warning("strategist.using_stub", reason="no_llm_configured")
            return self._stub(brief)
        prompt = (
            f"- Topic (tema): {brief.tema}\n"
            f"- Target audience / community to reach: {brief.publico_objetivo}\n"
            f"- Platform: {brief.red_social}\n"
            f"- Goal: {brief.objetivo}\n"
            f"- Brand tone: {brief.tono_marca}\n"
            f"- Language: {brief.idioma}\n"
            f"- Inbound intent stack (required): entretener → informacion → conexion"
        )
        try:
            data = llm.complete_json(_SYSTEM, prompt)
            return StrategyOutput(**data)
        except Exception as exc:
            logger.error("strategist.llm_error", error=str(exc))
            return self._stub(brief)

    def _stub(self, brief: BriefInput) -> StrategyOutput:
        """Estrategia fija de ejemplo para desarrollo sin API de modelo."""
        return StrategyOutput(
            tipo_post="educativo",
            hook=f"¿Sabias que {brief.tema.lower()} puede acelerar tus resultados?",
            mensaje_base=(
                f"Contenido {brief.objetivo} para {brief.publico_objetivo} en "
                f"{brief.red_social} con enfoque {brief.tono_marca}. "
                f"Atraemos, informamos y conectamos con esa comunidad."
            ),
            hashtags=["#IA", "#MarketingDigital", "#Automatizacion"],
        )
