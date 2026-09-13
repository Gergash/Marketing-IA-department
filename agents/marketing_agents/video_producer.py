"""VideoProducerAgent: elige N tomas desde transcript (auto por contexto o rangos manuales).

No descarga video: trabaja sobre ClipTranscript + CloudFootageRef y emite TakeProposal
con drive_file_id para el HITL pending_takes / corte diferido.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from .llm import get_llm
from .schemas import BriefInput, ManualTakeRange, StrategyOutput, TakeProposal
from .transcription_providers import ClipTranscript

logger = structlog.get_logger(__name__)

_MIN_TAKE_S = 2.0
_MAX_TAKE_S = 12.0
_MAX_TOTAL_S = 90.0
_ALLOWED_COUNTS = frozenset({5, 10, 15, 20, 30})

_SYSTEM = """\
You are an expert short-form audiovisual producer selecting the best spoken moments from long-form \
footage transcripts to build a vertical social reel.

Select EXACTLY {take_count} segments. Each segment duration MUST be between {_MIN_TAKE_S} and {_MAX_TAKE_S} seconds. \
The SUM of all segment durations MUST be between 6 and {_MAX_TOTAL_S} seconds.

Prioritize moments that match the editing goal and client context:
- Prices, offers, locations, brand messages, CTAs
- Clear hooks, questions, reveals, strong declarative lines
- Audience preferences from the brief

Mark exactly one segment as the hook (is_hook=true), preferably the strongest opening.

Return ONLY valid JSON:
{{
  "segments": [
    {{"clip_id": "<id>", "start_s": <float>, "end_s": <float>, "text": "<spoken>", "is_hook": <bool>, "score": <float>}}
  ]
}}
"""


class _ProducerSegment(BaseModel):
    clip_id: str
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    text: str = ""
    is_hook: bool = False
    score: float = 0.0


def _clip_id_to_file_id(footage_by_clip: dict[str, str], clip_id: str) -> str:
    return footage_by_clip.get(clip_id, "")


def _preview_url(file_id: str, start_s: float, end_s: float) -> str:
    from gateway.app.core.settings import get_settings

    base = get_settings().public_image_base_url.rstrip("/")
    return f"{base}/api/media/drive/{file_id}?start_s={start_s:.3f}&end_s={end_s:.3f}"


def _words_in_range(transcript: ClipTranscript, start_s: float, end_s: float) -> str:
    parts = [w.text for w in transcript.words if w.end_s > start_s and w.start_s < end_s]
    return " ".join(parts).strip()


def _score_relevance(text: str, editing_goal: str, brief: BriefInput) -> float:
    lowered = text.lower()
    score = 0.0
    keywords = (
        "precio",
        "pesos",
        "$",
        "ubic",
        "dirección",
        "direccion",
        "calle",
        "oferta",
        "descuento",
        "agenda",
        "reserva",
        "whatsapp",
        "llama",
        "compra",
        "promo",
    )
    for kw in keywords:
        if kw in lowered:
            score += 1.0
    goal = (editing_goal or "").lower()
    for token in goal.replace(",", " ").split():
        if len(token) > 3 and token in lowered:
            score += 0.5
    for token in (brief.tema + " " + brief.objetivo).lower().split():
        if len(token) > 3 and token in lowered:
            score += 0.25
    if "?" in lowered:
        score += 1.0
    return score


def _window_candidates(transcript: ClipTranscript, window_s: float = 8.0) -> list[_ProducerSegment]:
    if not transcript.words:
        return []
    t0 = transcript.words[0].start_s
    t1 = transcript.words[-1].end_s
    candidates: list[_ProducerSegment] = []
    cursor = t0
    while cursor + _MIN_TAKE_S <= t1:
        end = min(cursor + window_s, t1)
        if end - cursor < _MIN_TAKE_S:
            break
        text = _words_in_range(transcript, cursor, end)
        if text:
            candidates.append(
                _ProducerSegment(
                    clip_id=transcript.clip_id,
                    start_s=cursor,
                    end_s=end,
                    text=text,
                    score=0.0,
                )
            )
        cursor += window_s * 0.5
    return candidates


def _select_stub_auto(
    transcripts: list[ClipTranscript],
    brief: BriefInput,
    editing_goal: str,
    take_count: int,
) -> list[_ProducerSegment]:
    scored: list[_ProducerSegment] = []
    for tr in transcripts:
        for cand in _window_candidates(tr):
            cand.score = _score_relevance(cand.text, editing_goal, brief)
            scored.append(cand)
    if not scored:
        raise RuntimeError("insufficient transcript to propose takes")

    scored.sort(key=lambda s: s.score, reverse=True)
    selected: list[_ProducerSegment] = []
    used_spans: list[tuple[str, float, float]] = []
    total = 0.0
    for cand in scored:
        if len(selected) >= take_count:
            break
        dur = cand.end_s - cand.start_s
        if total + dur > _MAX_TOTAL_S:
            continue
        overlap = False
        for clip_id, a, b in used_spans:
            if cand.clip_id == clip_id and not (cand.end_s <= a or cand.start_s >= b):
                overlap = True
                break
        if overlap:
            continue
        selected.append(cand)
        used_spans.append((cand.clip_id, cand.start_s, cand.end_s))
        total += dur

    if len(selected) < min(take_count, 1):
        raise RuntimeError("could not select enough non-overlapping takes")

    # Rellenar hasta take_count con siguientes candidatos si cabe
    if len(selected) < take_count:
        for cand in scored:
            if len(selected) >= take_count:
                break
            if any(
                cand.clip_id == s.clip_id and abs(cand.start_s - s.start_s) < 0.5 for s in selected
            ):
                continue
            dur = cand.end_s - cand.start_s
            if sum(x.end_s - x.start_s for x in selected) + dur > _MAX_TOTAL_S:
                continue
            selected.append(cand)

    selected = selected[:take_count]
    selected.sort(key=lambda s: (s.clip_id, s.start_s))
    if selected:
        best = max(range(len(selected)), key=lambda i: selected[i].score)
        for i, seg in enumerate(selected):
            seg.is_hook = i == best
    return selected


def _from_manual(
    ranges: list[ManualTakeRange] | list[dict],
    transcripts: list[ClipTranscript],
    footage_by_file: dict[str, str],
    take_count: int,
) -> list[_ProducerSegment]:
    by_clip = {t.clip_id: t for t in transcripts}
    # Map file_id → clip_id (footage_by_file is clip_id → file_id)
    file_to_clip = {fid: cid for cid, fid in footage_by_file.items()}
    default_clip = transcripts[0].clip_id if transcripts else ""
    out: list[_ProducerSegment] = []
    for raw in ranges[:take_count]:
        r = raw if isinstance(raw, ManualTakeRange) else ManualTakeRange(**raw)
        start, end = float(r.start_s), float(r.end_s)
        if end <= start:
            continue
        dur = end - start
        if dur < _MIN_TAKE_S:
            end = start + _MIN_TAKE_S
            dur = _MIN_TAKE_S
        if dur > _MAX_TAKE_S:
            end = start + _MAX_TAKE_S
            dur = _MAX_TAKE_S
        clip_id = file_to_clip.get(r.file_id) or default_clip
        tr = by_clip.get(clip_id)
        text = _words_in_range(tr, start, end) if tr else ""
        out.append(
            _ProducerSegment(
                clip_id=clip_id,
                start_s=start,
                end_s=end,
                text=text,
                score=1.0,
            )
        )
    if not out:
        raise RuntimeError("manual_ranges produced no valid takes")
    out[0].is_hook = True
    return out


def _to_takes(
    segments: list[_ProducerSegment],
    footage_by_clip: dict[str, str],
) -> list[TakeProposal]:
    takes: list[TakeProposal] = []
    for idx, seg in enumerate(segments):
        file_id = _clip_id_to_file_id(footage_by_clip, seg.clip_id)
        duration_s = seg.end_s - seg.start_s
        takes.append(
            TakeProposal(
                id=f"take-{idx + 1}",
                clip_id=seg.clip_id,
                drive_file_id=file_id,
                source_clip_url=_preview_url(file_id, seg.start_s, seg.end_s) if file_id else "",
                trim_in=seg.start_s,
                trim_out=seg.end_s,
                duration_s=duration_s,
                transcript=seg.text,
                is_hook=seg.is_hook,
                score=seg.score,
                status="proposed",
                order=idx,
            )
        )
    return takes


class VideoProducerAgent:
    """Propone exactamente N tomas (auto o manual) para user_clip_reel cloud."""

    def run(
        self,
        transcripts: list[ClipTranscript],
        brief: BriefInput,
        strategy: StrategyOutput,
        *,
        footage_by_clip: dict[str, str],
        take_count: int = 10,
        selection_mode: str = "auto",
        editing_goal: str | None = None,
        manual_ranges: list[ManualTakeRange] | None = None,
        revision_notes: str | None = None,
    ) -> list[TakeProposal]:
        if take_count not in _ALLOWED_COUNTS:
            take_count = 10
        goal = (editing_goal or strategy.hook or brief.objetivo or "").strip()
        mode = (selection_mode or "auto").strip().lower()

        if mode == "manual":
            ranges = list(manual_ranges or [])
            segments = _from_manual(ranges, transcripts, footage_by_clip, take_count)
            return _to_takes(segments, footage_by_clip)

        llm = get_llm()
        if llm is None:
            logger.warning("video_producer.using_stub", reason="no_llm_configured")
            segments = _select_stub_auto(transcripts, brief, goal, take_count)
            return _to_takes(segments, footage_by_clip)

        system = _SYSTEM.format(
            take_count=take_count,
            _MIN_TAKE_S=_MIN_TAKE_S,
            _MAX_TAKE_S=_MAX_TAKE_S,
            _MAX_TOTAL_S=_MAX_TOTAL_S,
        )
        prompt = (
            f"- Editing goal: {goal}\n"
            f"- Audience: {brief.publico_objetivo}\n"
            f"- Topic: {brief.tema}\n"
            f"- Brand objective: {brief.objetivo}\n"
            f"- Strategy hook: {strategy.hook}\n"
            f"- Take count required: {take_count}\n"
            f"- Transcripts: {[(t.clip_id, t.text[:4000], [w.model_dump() for w in t.words[:400]]) for t in transcripts]}"
        )
        notes = (revision_notes or "").strip()
        if notes:
            prompt += f"\n- REVISION (highest priority): {notes}"

        try:
            data = llm.complete_json(system, prompt)
            segments = [_ProducerSegment(**seg) for seg in data["segments"]]
            if len(segments) > take_count:
                segments = segments[:take_count]
            if not segments:
                raise ValueError("empty segments")
            total = sum(s.end_s - s.start_s for s in segments)
            if total > _MAX_TOTAL_S or total < 6.0:
                raise ValueError(f"duration out of band: {total}")
            return _to_takes(segments, footage_by_clip)
        except Exception as exc:
            logger.error("video_producer.llm_error", error=str(exc))
            segments = _select_stub_auto(transcripts, brief, goal, take_count)
            return _to_takes(segments, footage_by_clip)
