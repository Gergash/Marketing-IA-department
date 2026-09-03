"""Agente estratega: traduce el brief en hook, mensaje y hashtags (LLM o fallback creativo)."""

import structlog

from .brand_manual import brand_prompt_block, brand_system_addendum
from .creative_fallback import creative_strategy_fallback, looks_like_meta_brief_dump
from .knowledge import inbound_system_addendum
from .llm import get_llm
from .schemas import BriefInput, StrategyOutput

logger = structlog.get_logger(__name__)

_SYSTEM = """\
You are an expert social media content strategist and creative director.
Given a marketing brief, write a platform-ready CONTENT ANGLE — not a summary of the brief.

Return ONLY valid JSON with exactly these fields:
{
  "tipo_post": "<one of: educativo | promocional | entretenimiento | informativo>",
  "hook":       "<attention-grabbing opening line spoken TO the audience, max 120 chars>",
  "mensaje_base": "<2-4 warm, concrete sentences about the product/event experience>",
  "hashtags":   ["<3-5 relevant hashtags with # prefix>"]
}

CRITICAL anti-literal rules (violations are rejected):
- NEVER paste briefing labels into the copy. Forbidden patterns include:
  "contenido ventas/branding/leads…", "para {audience} en {platform}", "con enfoque {tone}",
  "público objetivo", "acelerar tus resultados", "tono de marca".
- Goal, audience and tone are INPUT CONSTRAINTS, not words to print.
  Example: goal=ventas + audience=parejas + tone=cercano + tema=Día del Amor y Amistad
  → write romantic/experiential copy inviting couples to celebrate, NOT
    "Contenido ventas para parejas en instagram con enfoque cercano".
- Speak as the brand talking to the audience about the tema (product/event).
- Match the requested brand tone in VOICE (warm, formal, playful…), without naming the tone.
- Write complete sentences with correct spelling and accents in the language of 'idioma'.
- Hook entertains; mensaje_base informs with concrete sensory/benefit detail; imply connection.
""" + inbound_system_addendum(role="strategist")


class ContentStrategistAgent:
    """Define tipo de post, hook, mensaje base y hashtags según el brief (LLM o fallback creativo)."""

    def run(self, brief: BriefInput, *, user_notes: str | None = None) -> StrategyOutput:
        """Devuelve `StrategyOutput` desde el LLM o fallback creativo ante ausencia/error.

        `user_notes` llega del checkpoint interactivo: el usuario leyó la estrategia
        propuesta y pidió otra dirección.
        """
        llm = get_llm()
        if llm is None:
            logger.warning("strategist.using_creative_fallback", reason="no_llm_configured")
            return creative_strategy_fallback(brief)

        prompt = (
            f"- Product/event to promote (tema — write ABOUT this, do not invent other topics): {brief.tema}\n"
            f"- Audience to speak TO (do NOT print this label): {brief.publico_objetivo}\n"
            f"- Platform (adapt length/style; do NOT say the platform name in the copy): {brief.red_social}\n"
            f"- Business goal (shape the CTA intent; do NOT print the goal word): {brief.objetivo}\n"
            f"- Brand tone (match the VOICE; do NOT print the tone word): {brief.tono_marca}\n"
            f"- Language: {brief.idioma}\n"
            f"- Write as publishable social content, not as an internal strategy memo."
            + brand_prompt_block(brief.brand_context)
        )
        if user_notes and user_notes.strip():
            prompt += (
                "\n\nThe human reviewer read the previous strategy and asked for a different "
                "direction. Their instructions override the defaults above:\n"
                f"- {user_notes.strip()}"
            )
        system = _SYSTEM + brand_system_addendum(brief.brand_context)
        try:
            data = llm.complete_json(system, prompt, max_tokens=1200)
            out = StrategyOutput(**data)
            if looks_like_meta_brief_dump(out.hook) or looks_like_meta_brief_dump(out.mensaje_base):
                logger.warning(
                    "strategist.meta_dump_rejected",
                    hook=out.hook[:80],
                    mensaje=out.mensaje_base[:80],
                )
                return creative_strategy_fallback(brief)
            return out
        except Exception as exc:
            logger.error("strategist.llm_error", error=str(exc), error_type=type(exc).__name__)
            return creative_strategy_fallback(brief)
