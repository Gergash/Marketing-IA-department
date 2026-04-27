import structlog

from .llm import get_llm
from .schemas import CopyOutput, StrategyOutput

logger = structlog.get_logger(__name__)

_SYSTEM = """\
You are a professional social media copywriter.
Given a content strategy, write compelling post copy ready to publish.

Return ONLY valid JSON with exactly these fields:
{
  "copy_final": "<complete post text integrating hook and message; platform-appropriate length>",
  "hashtags":   ["<all hashtags to append including # prefix>"],
  "cta":        "<one clear call-to-action sentence>"
}

Rules:
- Write in the same language as the strategy (infer from hook/hashtags).
- LinkedIn: up to 1300 chars, paragraph breaks.
- Instagram / Facebook: up to 2200 chars, line breaks + emojis OK.
- X/Twitter: 280 chars max.
- TikTok: short, energetic, 150 chars.
- Always close the copy with the CTA embedded naturally, not as a separate paragraph.\
"""


class CopywriterAgent:
    def run(
        self,
        strategy: StrategyOutput,
        *,
        qa_feedback: list[str] | None = None,
    ) -> CopyOutput:
        llm = get_llm()
        if llm is None:
            logger.warning("copywriter.using_stub", reason="no_llm_configured")
            return self._stub(strategy, qa_feedback=qa_feedback)
        prompt = (
            f"- Post type: {strategy.tipo_post}\n"
            f"- Hook: {strategy.hook}\n"
            f"- Core message: {strategy.mensaje_base}\n"
            f"- Suggested hashtags: {', '.join(strategy.hashtags)}"
        )
        if qa_feedback:
            prompt += (
                "\n\nThe previous draft was rejected by QA/compliance. "
                "Revise the copy to fully address every point below (same JSON output shape):\n"
                + "\n".join(f"- {r}" for r in qa_feedback)
            )
        try:
            data = llm.complete_json(_SYSTEM, prompt)
            return CopyOutput(**data)
        except Exception as exc:
            logger.error("copywriter.llm_error", error=str(exc))
            return self._stub(strategy, qa_feedback=qa_feedback)

    def _stub(self, strategy: StrategyOutput, *, qa_feedback: list[str] | None = None) -> CopyOutput:
        copy_text = (
            f"{strategy.hook}\n\n"
            f"{strategy.mensaje_base}\n"
            "Con un flujo de agentes puedes pasar de idea a post en minutos."
        )
        if qa_feedback:
            lowered_fb = " ".join(qa_feedback).lower()
            if "exclamaciones" in lowered_fb or "formal" in lowered_fb:
                copy_text = copy_text.replace("!!!", ".")
            if "bloqueada" in lowered_fb or "palabra" in lowered_fb:
                for w in ("estafa", "fake", "garantizado 100%"):
                    copy_text = copy_text.replace(w, "[redacted]")
            copy_text += "\n\n(Nota: borrador ajustado según retroalimentación de QA.)"
        return CopyOutput(
            copy_final=copy_text,
            hashtags=strategy.hashtags + ["#Growth", "#SocialMedia"],
            cta="Escribe 'MVP' y te compartimos una demo del flujo.",
        )
