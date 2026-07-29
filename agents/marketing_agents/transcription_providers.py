"""Transcripción de clips de video: extracción de audio (ffmpeg) + Whisper con timestamps de palabra.

`STT_PROVIDER=whisper` (real, whisper-1 vía OpenAI) | `mock` (dev sin API real).
Todo el I/O externo (ffmpeg subprocess, llamada HTTP a Whisper) vive en funciones de módulo
reemplazables por monkeypatch en tests — nunca se ejecuta ffmpeg real ni red real en tests.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
import uuid
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

_MAX_CHUNK_BYTES = 25 * 1024 * 1024  # límite de tamaño de archivo de la Whisper API
_MAX_RETRIES = 2


class Word(BaseModel):
    """Palabra transcrita con timestamps absolutos (ya offset-corregidos si venía de un chunk)."""

    text: str
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)


class ClipTranscript(BaseModel):
    """Transcripción completa de un clip: texto + palabras con timestamps."""

    clip_id: str
    words: list[Word] = Field(default_factory=list)
    text: str = ""


def _extract_audio(video_path: Path) -> Path:
    """Extrae audio mono 16kHz a WAV vía ffmpeg (subprocess); mockeado en tests."""
    out_path = Path(tempfile.gettempdir()) / f"clip_audio_{uuid.uuid4().hex}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(out_path)],
        check=True,
        capture_output=True,
    )
    return out_path


def _file_size_bytes(path: Path) -> int:
    """Tamaño del archivo de audio extraído (helper aislado para monkeypatch en tests)."""
    return path.stat().st_size


def _probe_duration_seconds(audio_path: Path) -> float:
    """Duración del audio extraído vía ffprobe (subprocess); mockeado en tests."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _extract_chunk(audio_path: Path, start_s: float, end_s: float) -> Path:
    """Extrae el tramo [start_s, end_s) del audio vía ffmpeg (subprocess); mockeado en tests."""
    out_path = Path(tempfile.gettempdir()) / f"chunk_{uuid.uuid4().hex}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start_s), "-to", str(end_s), "-i", str(audio_path), str(out_path)],
        check=True,
        capture_output=True,
    )
    return out_path


def _whisper_call(
    audio_path: Path,
    api_key: str,
    *,
    start_s: float = 0.0,
    end_s: float | None = None,
) -> dict:
    """Llama a whisper-1 (verbose_json, timestamps de palabra); mockeado en tests.

    Si `end_s` viene dado, primero extrae ese tramo del audio antes de transcribir (chunking >25MB).
    """
    from openai import OpenAI

    segment_path = audio_path
    if end_s is not None:
        segment_path = _extract_chunk(audio_path, start_s, end_s)

    client = OpenAI(api_key=api_key)
    with open(segment_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )
    data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
    return {
        "text": data.get("text", ""),
        "words": [
            {"word": w.get("word", ""), "start": w.get("start", 0.0), "end": w.get("end", 0.0)}
            for w in (data.get("words") or [])
        ],
    }


def _chunk_plan(total_duration_s: float, size_bytes: int) -> list[tuple[float, float]]:
    """Calcula ventanas (start_s, end_s) asumiendo bitrate uniforme, respetando el límite de 25MB."""
    n_chunks = math.ceil(size_bytes / _MAX_CHUNK_BYTES)
    chunk_duration = total_duration_s / n_chunks
    plan: list[tuple[float, float]] = []
    start = 0.0
    for _ in range(n_chunks):
        end = min(total_duration_s, start + chunk_duration)
        plan.append((start, end))
        start = end
    return plan


def _mock_transcribe(clip_id: str) -> ClipTranscript:
    """Transcripción determinística sin llamadas externas (dev sin API real)."""
    words = [
        Word(text="hola", start_s=0.0, end_s=0.4),
        Word(text="mundo", start_s=0.4, end_s=0.9),
    ]
    return ClipTranscript(clip_id=clip_id, words=words, text="hola mundo")


def _to_transcript(clip_id: str, raw: dict) -> ClipTranscript:
    words = [Word(text=w["word"], start_s=w["start"], end_s=w["end"]) for w in raw["words"]]
    return ClipTranscript(clip_id=clip_id, words=words, text=raw.get("text", ""))


def _to_transcript_chunked(clip_id: str, raws: list[tuple[float, dict]]) -> ClipTranscript:
    """Concatena resultados de chunks offset-corrigiendo cada timestamp de palabra por el inicio del chunk."""
    words: list[Word] = []
    texts: list[str] = []
    for offset_s, raw in raws:
        for w in raw["words"]:
            words.append(Word(text=w["word"], start_s=w["start"] + offset_s, end_s=w["end"] + offset_s))
        if raw.get("text"):
            texts.append(raw["text"])
    return ClipTranscript(clip_id=clip_id, words=words, text=" ".join(texts).strip())


def transcribe_clip(
    clip_id: str,
    video_path: Path,
    *,
    stt_provider: str | None = None,
) -> ClipTranscript | None:
    """Transcribe un clip; devuelve None (excluido) si Whisper falla tras reintentos."""
    from gateway.app.core.settings import get_settings

    s = get_settings()
    provider = (stt_provider or s.stt_provider).strip().lower()

    if provider == "mock":
        return _mock_transcribe(clip_id)

    api_key = s.openai_api_key
    if not api_key:
        logger.error("transcription.missing_api_key", clip_id=clip_id)
        return None

    try:
        audio_path = _extract_audio(video_path)
    except Exception as exc:
        logger.error("transcription.ffmpeg_extract_failed", clip_id=clip_id, error=str(exc))
        return None

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            size_bytes = _file_size_bytes(audio_path)
            if size_bytes <= _MAX_CHUNK_BYTES:
                raw = _whisper_call(audio_path, api_key)
                return _to_transcript(clip_id, raw)

            duration_s = _probe_duration_seconds(audio_path)
            plan = _chunk_plan(duration_s, size_bytes)
            raws = [(start_s, _whisper_call(audio_path, api_key, start_s=start_s, end_s=end_s)) for start_s, end_s in plan]
            return _to_transcript_chunked(clip_id, raws)
        except Exception as exc:
            last_error = exc
            logger.warning("transcription.attempt_failed", clip_id=clip_id, attempt=attempt, error=str(exc))

    logger.error("transcription.excluded_after_retries", clip_id=clip_id, error=str(last_error))
    return None


def transcribe_clips(
    clips: list[tuple[str, Path]],
    *,
    stt_provider: str | None = None,
) -> list[ClipTranscript]:
    """Transcribe múltiples clips; excluye los que fallan; falla el run solo si TODOS fallan."""
    results: list[ClipTranscript] = []
    for clip_id, video_path in clips:
        transcript = transcribe_clip(clip_id, video_path, stt_provider=stt_provider)
        if transcript is not None:
            results.append(transcript)

    if not results:
        raise RuntimeError("transcription_failed: all clips excluded, no usable transcripts")

    return results
