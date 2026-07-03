"""Agente de guion de video: expande estrategia+copy en 3-5 escenas narradas para un Reel (LLM o stub)."""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from .llm import get_llm
from .schemas import BriefInput, CopyOutput, StrategyOutput

logger = structlog.get_logger(__name__)

# Ritmo de habla estimado (español) usado para orientar la banda 15-30s al redactar el guion.
_WORDS_PER_SECOND = 2.5

_SYSTEM = """\
You are an expert short-form vertical video scriptwriter for Instagram Reels.
Given an approved content strategy and post copy, produce a 3-5 scene video script for narration + on-screen text.

Return ONLY valid JSON with exactly these fields:
{
  "hook": "<opening line spoken in scene 1, max 100 chars>",
  "cta":  "<closing call-to-action spoken in the last scene, max 80 chars>",
  "scenes": [
    {
      "headline": "<short on-screen overlay text, max 60 chars, complete phrase, perfect spelling>",
      "subline": "<optional supporting on-screen text, max 60 chars, or empty string>",
      "narration": "<spoken narration line for this scene, natural complete sentence>",
      "visual_prompt": "<background visual description for image generation; no text, no letters, no watermark>"
    }
  ]
}

Rules:
- Produce between 3 and 5 scenes total; the LAST scene MUST be the CTA scene (its narration is the closing CTA).
- Target a TOTAL narration length matching a 15-30 second reel (~2.5 spoken words per second).
- Write in the language specified by 'idioma'.
- Never include emojis unless the tone explicitly calls for them.\
"""


class ScriptScene(BaseModel):
    """Una escena del guion: overlay de texto + línea de narración + prompt visual de fondo."""

    headline: str = Field(min_length=1)
    subline: str = ""
    narration: str = Field(min_length=1)
    visual_prompt: str = Field(min_length=1)


class VideoScript(BaseModel):
    """Guion completo de un reel: hook, CTA y 3-5 escenas narradas (la última es la escena de CTA)."""

    hook: str = Field(min_length=1)
    cta: str = Field(min_length=1)
    scenes: list[ScriptScene] = Field(min_length=3, max_length=5)


class VideoScriptAgent:
    """Genera el guion de video (hook, escenas narradas, CTA) desde estrategia y copy aprobados (LLM o stub)."""

    def run(self, brief: BriefInput, strategy: StrategyOutput, copy: CopyOutput) -> VideoScript:
        """Devuelve `VideoScript` desde el LLM configurado o `_stub` ante ausencia de LLM o error."""
        llm = get_llm()
        if llm is None:
            logger.warning("video_script.using_stub", reason="no_llm_configured")
            return self._stub(brief, strategy, copy)
        prompt = (
            f"- Topic (tema): {brief.tema}\n"
            f"- Target audience: {brief.publico_objetivo}\n"
            f"- Platform: {brief.red_social}\n"
            f"- Strategy hook: {strategy.hook}\n"
            f"- Core message: {strategy.mensaje_base}\n"
            f"- Approved copy: {copy.copy_final}\n"
            f"- CTA: {copy.cta}\n"
            f"- Language: {brief.idioma}"
        )
        try:
            data = llm.complete_json(_SYSTEM, prompt)
            return VideoScript(**data)
        except Exception as exc:
            logger.error("video_script.llm_error", error=str(exc))
            return self._stub(brief, strategy, copy)

    def _stub(self, brief: BriefInput, strategy: StrategyOutput, copy: CopyOutput) -> VideoScript:
        """Guion determinista de 4 escenas para desarrollo sin LLM, calibrado dentro de la banda 15-30s."""
        tema = brief.tema
        scenes = [
            ScriptScene(
                headline=strategy.hook[:60],
                narration=f"¿Sabias que {tema} puede cambiar tu forma de trabajar?",
                visual_prompt=(
                    f"Cinematic vertical shot representing {tema}, no text, no letters, "
                    "no watermark, clean composition"
                ),
            ),
            ScriptScene(
                headline="Un problema comun",
                narration=f"Muchos equipos pierden horas cada semana en tareas repetitivas de {tema}.",
                visual_prompt=(
                    f"Editorial vertical photo showing a daily struggle related to {tema}, "
                    "no text, no letters, no watermark"
                ),
            ),
            ScriptScene(
                headline=(copy.headline_for_image[:60] or strategy.hook[:60]),
                subline=copy.subline_for_image[:60],
                narration="Con agentes de IA automatizas el proceso de principio a fin.",
                visual_prompt=(
                    f"Modern vertical scene showing automation benefits for {brief.publico_objetivo}, "
                    "no text, no letters, no watermark"
                ),
            ),
            ScriptScene(
                headline=copy.cta[:60],
                narration=copy.cta,
                visual_prompt=(
                    f"Vertical call-to-action scene, bright and inviting, related to {tema}, "
                    "no text, no letters, no watermark"
                ),
            ),
        ]
        return VideoScript(hook=strategy.hook, cta=copy.cta, scenes=scenes)
