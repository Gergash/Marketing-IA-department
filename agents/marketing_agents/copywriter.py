"""Agente copywriter: genera texto de post desde la estrategia (LLM o fallback creativo)."""

import structlog

from .brand_manual import brand_prompt_block, brand_system_addendum
from .creative_fallback import creative_copy_fallback, looks_like_meta_brief_dump
from .knowledge import inbound_system_addendum
from .llm import get_llm
from .schemas import BriefInput, CopyOutput, StrategyOutput

logger = structlog.get_logger(__name__)

_SYSTEM = """\
You are a professional social media copywriter and brand storyteller.
Given a content strategy AND the original brief, write publishable copy that feels
human, complete, and true to the requested tone. Invent nothing about prices or
unavailable offers; stay faithful to the tema (product/event).

Return ONLY valid JSON with exactly these fields:
{
  "copy_final": "<complete post CAPTION: 3–6 short paragraphs (platform-appropriate length). Must include: hook, sensory/benefit body, soft CTA. NO hashtag block at the end (hashtags go in the hashtags array)>",
  "headline_for_image": "<1 short complete sentence for image overlay, max 90 chars, perfect spelling and accents>",
  "subline_for_image": "<optional supporting line for overlay, max 70 chars, complete phrase or empty string>",
  "hashtags":   ["<3-5 hashtags with # prefix — ALWAYS required>"],
  "cta":        "<short call-to-action for the caption, max 45 chars — NOT an on-image button>"
}

Creative rules:
- Match the brand tone in VOICE (cercano = warm/conversational; formal = polished; etc.) without naming the tone.
- Never dump briefing fields into the copy. Forbidden: "contenido ventas…", "para {audience} en {platform}", "con enfoque {tone}", "acelerar tus resultados".
- headline_for_image / subline_for_image appear ON the image: punchy, emotional, complete — not the full caption, not truncated mid-word.
- copy_final must be SUBSTANTIVE: more than one sentence; paint the experience; invite connection.
- Do NOT design an on-image CTA button; CTA lives in the caption.
- ALWAYS return 3–5 hashtags. Never invent URLs.
- LinkedIn: up to 1300 chars. Instagram/Facebook: up to 2200. X: 280 max. TikTok: ~150.
- Close copy_final with a natural CTA (comment, DM, reserve, tag someone).
""" + inbound_system_addendum(role="copywriter")


class CopywriterAgent:
    """Genera el texto final del post a partir de la estrategia (LLM o fallback creativo)."""

    def run(
        self,
        strategy: StrategyOutput,
        *,
        brief: BriefInput | None = None,
        qa_feedback: list[str] | None = None,
        brand_context: str = "",
    ) -> CopyOutput:
        """Produce `CopyOutput` vía LLM o fallback creativo si no hay LLM / falla / meta-dump."""
        llm = get_llm()
        if llm is None:
            logger.warning("copywriter.using_creative_fallback", reason="no_llm_configured")
            return self._fallback(strategy, brief=brief, qa_feedback=qa_feedback)

        prompt = (
            f"- Post type: {strategy.tipo_post}\n"
            f"- Hook (may refine, keep spirit): {strategy.hook}\n"
            f"- Core message: {strategy.mensaje_base}\n"
            f"- Suggested hashtags: {', '.join(strategy.hashtags)}\n"
        )
        if brief is not None:
            prompt += (
                f"- Tema / product-event: {brief.tema}\n"
                f"- Speak TO this audience (do not print the label): {brief.publico_objetivo}\n"
                f"- Platform: {brief.red_social}\n"
                f"- Goal intent (do not print the word): {brief.objetivo}\n"
                f"- Tone VOICE to match (do not print the word): {brief.tono_marca}\n"
                f"- Language: {brief.idioma}\n"
            )
        prompt += (
            "- Structure copy_final as: Entretener → Información concreta → Conexión/CTA.\n"
            "- Write a FULL caption people would actually want to read; not a brief summary."
            + brand_prompt_block(brand_context)
        )
        if qa_feedback:
            prompt += (
                "\n\nThe previous draft was rejected by QA/compliance. "
                "Revise the copy to fully address every point below (same JSON output shape):\n"
                + "\n".join(f"- {r}" for r in qa_feedback)
            )
        system = _SYSTEM + brand_system_addendum(brand_context)
        try:
            data = llm.complete_json(system, prompt, max_tokens=1800)
            out = CopyOutput(**data)
            out = self._ensure_overlay_fields(out, strategy)
            if self._is_weak_or_meta(out):
                logger.warning(
                    "copywriter.meta_or_weak_rejected",
                    headline=out.headline_for_image[:80],
                    subline=out.subline_for_image[:80],
                )
                return self._fallback(strategy, brief=brief, qa_feedback=qa_feedback)
            return out
        except Exception as exc:
            logger.error("copywriter.llm_error", error=str(exc), error_type=type(exc).__name__)
            return self._fallback(strategy, brief=brief, qa_feedback=qa_feedback)

    def _is_weak_or_meta(self, out: CopyOutput) -> bool:
        blob = " ".join(
            [
                out.copy_final or "",
                out.headline_for_image or "",
                out.subline_for_image or "",
            ]
        )
        if looks_like_meta_brief_dump(blob):
            return True
        # Caption demasiado corto = el modelo se quedó en una línea literal
        if len((out.copy_final or "").strip()) < 80:
            return True
        return False

    def _fallback(
        self,
        strategy: StrategyOutput,
        *,
        brief: BriefInput | None,
        qa_feedback: list[str] | None,
    ) -> CopyOutput:
        if brief is None:
            # Sin brief: construir uno mínimo desde la estrategia para no volver al stub meta.
            brief = BriefInput(
                tema=strategy.hook or "esta experiencia",
                publico_objetivo="nuestra comunidad",
                red_social="instagram",
                objetivo="branding",
                tono_marca="cercano",
            )
        out = creative_copy_fallback(brief, strategy, qa_feedback=qa_feedback)
        return self._ensure_overlay_fields(out, strategy)

    def _ensure_overlay_fields(self, out: CopyOutput, strategy: StrategyOutput) -> CopyOutput:
        """Rellena headline/subline de overlay y garantiza hashtags para la descripción."""
        from .caption import ensure_hashtags
        from .overlay_text import truncate_at_sentence

        if not (out.headline_for_image or "").strip():
            out.headline_for_image = truncate_at_sentence(strategy.hook, 90)
        if not (out.subline_for_image or "").strip() and strategy.mensaje_base:
            # No usar mensaje_base meta como subline
            if not looks_like_meta_brief_dump(strategy.mensaje_base):
                out.subline_for_image = truncate_at_sentence(strategy.mensaje_base, 70)
        out.cta = truncate_at_sentence(out.cta, 45)
        out.hashtags = ensure_hashtags(out.hashtags, fallback=strategy.hashtags)
        return out
