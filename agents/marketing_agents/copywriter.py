"""Agente copywriter: genera texto de post desde la estrategia (LLM o stub)."""

import structlog

from .knowledge import inbound_system_addendum
from .llm import get_llm
from .schemas import CopyOutput, StrategyOutput

logger = structlog.get_logger(__name__)

_SYSTEM = """\
You are a professional social media copywriter using inbound marketing principles.
Given a content strategy, write compelling post copy ready to publish that reaches
the intended community and moves Entretener → Informacion → Conexion.

Return ONLY valid JSON with exactly these fields:
{
  "copy_final": "<complete post text integrating hook and message; platform-appropriate length>",
  "headline_for_image": "<1-2 SHORT complete sentences for image overlay, max 100 chars, perfect spelling>",
  "subline_for_image": "<optional supporting line for overlay, max 80 chars, complete sentence or empty string>",
  "hashtags":   ["<all hashtags to append including # prefix>"],
  "cta":        "<short call-to-action for button, max 45 chars>"
}

Rules:
- Write in the same language as the strategy (infer from hook/hashtags).
- headline_for_image and subline_for_image MUST use correct spelling and grammar; never cut words mid-syllable.
- headline_for_image is what appears ON the image — keep it punchy, not the full post.
- LinkedIn: up to 1300 chars for copy_final, paragraph breaks.
- Instagram / Facebook: up to 2200 chars for copy_final, line breaks + emojis OK.
- X/Twitter: copy_final 280 chars max.
- TikTok: short, energetic, copy_final 150 chars.
- Always close copy_final with the CTA embedded naturally, not as a separate paragraph.
- CTA must invite CONEXION (comment, save, DM, join community), not only hard sell.
""" + inbound_system_addendum(role="copywriter")


class CopywriterAgent:
    """Genera el texto final del post a partir de la estrategia (LLM o stub); admite revisiones por feedback de QA."""

    def run(
        self,
        strategy: StrategyOutput,
        *,
        qa_feedback: list[str] | None = None,
    ) -> CopyOutput:
        """Produce `CopyOutput` vía LLM configurado o `_stub` si no hay LLM o falla la llamada."""
        llm = get_llm()
        if llm is None:
            logger.warning("copywriter.using_stub", reason="no_llm_configured")
            return self._stub(strategy, qa_feedback=qa_feedback)
        prompt = (
            f"- Post type: {strategy.tipo_post}\n"
            f"- Hook: {strategy.hook}\n"
            f"- Core message: {strategy.mensaje_base}\n"
            f"- Suggested hashtags: {', '.join(strategy.hashtags)}\n"
            f"- Structure copy_final as: Entretener → Informacion → Conexion"
        )
        if qa_feedback:
            prompt += (
                "\n\nThe previous draft was rejected by QA/compliance. "
                "Revise the copy to fully address every point below (same JSON output shape):\n"
                + "\n".join(f"- {r}" for r in qa_feedback)
            )
        try:
            data = llm.complete_json(_SYSTEM, prompt)
            out = CopyOutput(**data)
            return self._ensure_overlay_fields(out, strategy)
        except Exception as exc:
            logger.error("copywriter.llm_error", error=str(exc))
            return self._stub(strategy, qa_feedback=qa_feedback)

    def _ensure_overlay_fields(self, out: CopyOutput, strategy: StrategyOutput) -> CopyOutput:
        """Rellena headline/subline de overlay si el LLM no los devolvió."""
        from .overlay_text import truncate_at_sentence

        if not out.headline_for_image.strip():
            out.headline_for_image = truncate_at_sentence(strategy.hook, 100)
        if not out.subline_for_image.strip() and strategy.mensaje_base:
            out.subline_for_image = truncate_at_sentence(strategy.mensaje_base, 80)
        out.cta = truncate_at_sentence(out.cta, 45)
        return out

    def _stub(self, strategy: StrategyOutput, *, qa_feedback: list[str] | None = None) -> CopyOutput:
        """Salida determinista de desarrollo; aplica transformaciones simples si hay feedback de QA."""
        copy_text = (
            f"{strategy.hook}\n\n"
            f"{strategy.mensaje_base}\n"
            "¿Te pasa lo mismo en tu comunidad? Cuéntanos en comentarios."
        )
        if qa_feedback:
            lowered_fb = " ".join(qa_feedback).lower()
            if "exclamaciones" in lowered_fb or "formal" in lowered_fb:
                copy_text = copy_text.replace("!!!", ".")
            if "bloqueada" in lowered_fb or "palabra" in lowered_fb:
                for w in ("estafa", "fake", "garantizado 100%"):
                    copy_text = copy_text.replace(w, "[redacted]")
            copy_text += "\n\n(Nota: borrador ajustado según retroalimentación de QA.)"
        out = CopyOutput(
            copy_final=copy_text,
            headline_for_image=strategy.hook[:100],
            subline_for_image=strategy.mensaje_base[:80] if strategy.mensaje_base else "",
            hashtags=strategy.hashtags + ["#Growth", "#SocialMedia"],
            cta="Comenta y conectemos.",
        )
        return self._ensure_overlay_fields(out, strategy)
