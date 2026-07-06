"""ClipEditorAgent: hook-scored selection de segmentos de video entre clips transcritos (LLM o stub).

Selecciona un subconjunto ordenado de spans cronologicos, respetando la banda 6-60s
(`_MIN_CLIP_S`/`_MAX_CLIP_S`) que solo aplica al flujo `user_clip_reel` (nunca al reel
generado, cuya banda 15-30s vive en video_timeline.py).
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from .llm import get_llm
from .schemas import BriefInput, StrategyOutput
from .transcription_providers import ClipTranscript

logger = structlog.get_logger(__name__)

_MIN_CLIP_S = 6.0
_MAX_CLIP_S = 60.0

# Heuristicas de hook: brevedad/declaratividad, pregunta/numero/revelacion/tension, ritmo natural.
_QUESTION_WORDS = ("qué", "que", "cómo", "como", "por qué", "porque", "cuál", "cual", "sabías", "sabias")
_REVEAL_WORDS = (
    "secreto", "nunca", "increíble", "increible", "sorprendente", "revela", "descubre", "error", "nadie",
)
_HOOK_MAX_DURATION_S = 3.5
_PACE_MIN_WPS = 2.0
_PACE_MAX_WPS = 4.0

_SYSTEM = """\
You are an expert short-form video editor selecting the best spoken segments across multiple raw clips \
to build a single vertical short-form reel from user-provided footage.

Given transcripts (with word-level timestamps) from one or more clips, select an ordered list of \
segments (spanning one or more clips) whose combined duration is between 6 and 60 seconds. \
Score candidate spans as a potential "hook" (opening segment) using these rules:
- Brevity/declarativeness in the first ~3 seconds
- Presence of a question, a number, or a reveal/tension word
- Natural speaking pace (not too slow, not too fast)
Mark exactly one segment as the hook (is_hook=true), preferably the highest-scoring one.

Return ONLY valid JSON with exactly this shape:
{
  "segments": [
    {"clip_id": "<id>", "start_s": <float>, "end_s": <float>, "text": "<spoken text>", "is_hook": <bool>}
  ]
}
"""


class SelectedSegment(BaseModel):
    """Un span seleccionado de un clip fuente para el reel final."""

    clip_id: str
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    text: str = ""
    is_hook: bool = False


def _clip_span(transcript: ClipTranscript) -> tuple[float, float, str] | None:
    """Extrae (start_s, end_s, text) del rango completo de palabras del clip; None si esta en silencio."""
    if not transcript.words:
        return None
    start = transcript.words[0].start_s
    end = transcript.words[-1].end_s
    return start, end, transcript.text


def _score_hook(text: str, duration_s: float) -> float:
    """Puntua un span como candidato a hook segun brevedad, señales de pregunta/numero/revelacion y ritmo."""
    lowered = text.lower()
    score = 0.0

    if duration_s <= _HOOK_MAX_DURATION_S:
        score += 1.0

    if "?" in lowered or any(w in lowered for w in _QUESTION_WORDS):
        score += 2.0

    if any(ch.isdigit() for ch in lowered):
        score += 1.0

    if any(w in lowered for w in _REVEAL_WORDS):
        score += 1.0

    words = lowered.split()
    if words and duration_s > 0:
        pace = len(words) / duration_s
        if _PACE_MIN_WPS <= pace <= _PACE_MAX_WPS:
            score += 0.5

    return score


def _select_stub(transcripts: list[ClipTranscript]) -> list[SelectedSegment]:
    """Heuristica deterministica: acumula spans en orden cronologico hasta llenar la banda 6-60s.

    Si el ultimo span excede el presupuesto restante, se recorta (no se descarta) para
    aterrizar exactamente en el limite superior de la banda.
    """
    spans: list[tuple[str, float, float, str, float]] = []
    for transcript in transcripts:
        span = _clip_span(transcript)
        if span is None:
            continue
        start, end, text = span
        duration = end - start
        if duration <= 0:
            continue
        spans.append((transcript.clip_id, start, end, text, duration))

    total_available = sum(s[4] for s in spans)
    if total_available < _MIN_CLIP_S:
        raise RuntimeError(
            f"insufficient footage (need >= {_MIN_CLIP_S:.0f}s): only {total_available:.1f}s available"
        )

    selected: list[SelectedSegment] = []
    accumulated = 0.0
    for clip_id, start, end, text, duration in spans:
        if accumulated >= _MAX_CLIP_S:
            break
        remaining_budget = _MAX_CLIP_S - accumulated
        if duration > remaining_budget:
            end = start + remaining_budget
            duration = remaining_budget
        selected.append(SelectedSegment(clip_id=clip_id, start_s=start, end_s=end, text=text))
        accumulated += duration

    if selected:
        scores = [_score_hook(seg.text, seg.end_s - seg.start_s) for seg in selected]
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        selected[best_idx] = selected[best_idx].model_copy(update={"is_hook": True})

    return selected


class ClipEditorAgent:
    """Selecciona segmentos de reel desde transcripciones de clips de usuario (LLM o stub deterministico)."""

    def run(
        self,
        transcripts: list[ClipTranscript],
        brief: BriefInput,
        strategy: StrategyOutput,
    ) -> list[SelectedSegment]:
        """Devuelve la lista ordenada de `SelectedSegment` seleccionada; propaga error de footage insuficiente."""
        llm = get_llm()
        if llm is None:
            logger.warning("clip_editor.using_stub", reason="no_llm_configured")
            return _select_stub(transcripts)

        prompt = (
            f"- Topic (tema): {brief.tema}\n"
            f"- Strategy hook: {strategy.hook}\n"
            f"- Core message: {strategy.mensaje_base}\n"
            f"- Transcripts (clip_id, words with start_s/end_s): "
            f"{[(t.clip_id, [w.model_dump() for w in t.words]) for t in transcripts]}"
        )
        try:
            data = llm.complete_json(_SYSTEM, prompt)
            segments = [SelectedSegment(**seg) for seg in data["segments"]]
            if not segments:
                raise ValueError("empty segments from LLM")
            total_duration = sum(seg.end_s - seg.start_s for seg in segments)
            if not (_MIN_CLIP_S <= total_duration <= _MAX_CLIP_S):
                raise ValueError(f"LLM segment duration out of band: {total_duration}")
            return segments
        except Exception as exc:
            logger.error("clip_editor.llm_error", error=str(exc))
            return _select_stub(transcripts)
