"""Footage en Google Drive sin materializar el máster completo en disco.

- Lista videos de una carpeta → CloudFootageRef
- Extrae solo audio vía stream ffmpeg → Whisper
- Corta spans cortos (ffmpeg -ss/-t) solo al renderizar
"""

from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

import httpx
import structlog
from sqlalchemy.orm import Session

from agents.marketing_agents.schemas import CloudFootageRef
from agents.marketing_agents.transcription_providers import (
    ClipTranscript,
    _chunk_plan,
    _file_size_bytes,
    _mock_transcribe,
    _probe_duration_seconds,
    _to_transcript,
    _to_transcript_chunked,
    _whisper_call,
)
from gateway.app.core.settings import get_settings

logger = structlog.get_logger(__name__)

_STATIC_CLIPS_DIR = Path(__file__).resolve().parents[2] / "static" / "uploads" / "clips"
_DRIVE_MEDIA_URL = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"


def get_drive_access_token(db: Session, tenant_id: str) -> str:
    """Access token Google fresco para el tenant (reusa drive_source)."""
    from agents.marketing_agents.drive_source import _get_token_row, _refresh_access_token

    token_row = _get_token_row(db, tenant_id)
    return _refresh_access_token(db, token_row)


def list_cloud_footage(db: Session, tenant_id: str, folder_id: str) -> list[CloudFootageRef]:
    """Lista videos de la carpeta Drive sin descargar bytes."""
    from agents.marketing_agents.drive_source import _list_folder_files

    access_token = get_drive_access_token(db, tenant_id)
    files = _list_folder_files(access_token, folder_id)
    if not files:
        raise RuntimeError("no_clips_found: la carpeta de Drive está vacía")

    video_files = [f for f in files if (f.get("mimeType") or "").startswith("video/")]
    if not video_files:
        raise RuntimeError("no_clips_found: la carpeta no contiene archivos de video")

    refs: list[CloudFootageRef] = []
    for f in video_files:
        refs.append(
            CloudFootageRef(
                provider="google_drive",
                file_id=f["id"],
                name=f.get("name") or f["id"],
                mime_type=f.get("mimeType") or "video/*",
                clip_id=uuid.uuid4().hex,
            )
        )
    return refs


def _drive_media_url(file_id: str) -> str:
    return _DRIVE_MEDIA_URL.format(file_id=file_id)


def _ffmpeg_headers(access_token: str) -> str:
    return f"Authorization: Bearer {access_token}\r\n"


def extract_audio_from_drive(access_token: str, file_id: str) -> Path:
    """Stream Drive → ffmpeg → WAV mono 16kHz en temp (sin guardar el MP4 maestro)."""
    out_path = Path(tempfile.gettempdir()) / f"drive_audio_{uuid.uuid4().hex}.wav"
    cmd = [
        "ffmpeg",
        "-y",
        "-headers",
        _ffmpeg_headers(access_token),
        "-i",
        _drive_media_url(file_id),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def cut_span_from_drive(
    access_token: str,
    file_id: str,
    *,
    start_s: float,
    duration_s: float,
    dest_path: Path,
) -> Path:
    """Materializa solo [start_s, start_s+duration_s) desde Drive a un MP4 corto local."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(max(0.0, start_s)),
        "-headers",
        _ffmpeg_headers(access_token),
        "-i",
        _drive_media_url(file_id),
        "-t",
        str(max(0.1, duration_s)),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(dest_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest_path


def cut_preview_from_drive(
    access_token: str,
    file_id: str,
    *,
    start_s: float,
    end_s: float,
) -> Path:
    """Preview corto on-demand (temp); no persiste en static/."""
    duration = max(0.1, end_s - start_s)
    # Cap preview a 20s para no saturar
    duration = min(duration, 20.0)
    out = Path(tempfile.gettempdir()) / f"drive_preview_{uuid.uuid4().hex}.mp4"
    return cut_span_from_drive(
        access_token,
        file_id,
        start_s=start_s,
        duration_s=duration,
        dest_path=out,
    )


def shorts_dir_for_run(run_id: int) -> Path:
    path = _STATIC_CLIPS_DIR / str(run_id) / "shorts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def transcribe_cloud_footage(
    footage: list[CloudFootageRef],
    access_token: str,
    *,
    stt_provider: str | None = None,
) -> list[ClipTranscript]:
    """Transcribe cada archivo Drive vía audio-only; excluye fallidos; falla si ninguno sirve."""
    s = get_settings()
    provider = (stt_provider or s.stt_provider).strip().lower()
    results: list[ClipTranscript] = []

    for ref in footage:
        clip_id = ref.clip_id or ref.file_id
        if provider == "mock":
            results.append(_mock_transcribe(clip_id))
            continue

        api_key = s.openai_api_key
        if not api_key:
            logger.error("cloud_footage.missing_api_key", file_id=ref.file_id)
            continue

        audio_path: Path | None = None
        try:
            audio_path = extract_audio_from_drive(access_token, ref.file_id)
            size_bytes = _file_size_bytes(audio_path)
            if size_bytes <= 25 * 1024 * 1024:
                raw = _whisper_call(audio_path, api_key)
                results.append(_to_transcript(clip_id, raw))
            else:
                duration_s = _probe_duration_seconds(audio_path)
                plan = _chunk_plan(duration_s, size_bytes)
                raws = [
                    (start_s, _whisper_call(audio_path, api_key, start_s=start_s, end_s=end_s))
                    for start_s, end_s in plan
                ]
                results.append(_to_transcript_chunked(clip_id, raws))
        except Exception as exc:
            logger.error("cloud_footage.transcribe_failed", file_id=ref.file_id, error=str(exc))
        finally:
            if audio_path and audio_path.exists():
                try:
                    audio_path.unlink()
                except OSError:
                    pass

    if not results:
        raise RuntimeError("transcription_failed: all cloud footage excluded, no usable transcripts")
    return results


def materialize_accepted_shorts(
    db: Session,
    tenant_id: str,
    run_id: int,
    takes: list,
) -> dict[str, str]:
    """Corta spans accepted desde Drive a shorts locales; devuelve take_id → public URL path local."""
    from agents.marketing_agents.clip_assets import clip_public_url
    from agents.marketing_agents.schemas import TakeProposal

    access_token = get_drive_access_token(db, tenant_id)
    out_dir = shorts_dir_for_run(run_id)
    url_by_take: dict[str, str] = {}

    for take in takes:
        if not isinstance(take, TakeProposal):
            take = TakeProposal(**take) if isinstance(take, dict) else take
        if take.status != "accepted":
            continue
        file_id = take.drive_file_id
        if not file_id:
            # Ya tiene URL local (legacy download path)
            if take.source_clip_url:
                url_by_take[take.id] = take.source_clip_url
            continue
        dest = out_dir / f"{take.id}.mp4"
        cut_span_from_drive(
            access_token,
            file_id,
            start_s=take.trim_in,
            duration_s=take.duration_s,
            dest_path=dest,
        )
        url_by_take[take.id] = clip_public_url(str(dest))
        logger.info("cloud_footage.short_ready", take_id=take.id, path=str(dest))

    return url_by_take


def open_drive_media_stream(access_token: str, file_id: str) -> httpx.Response:
    """Abre stream HTTP del media Drive (útil para proxies); caller debe cerrar."""
    client = httpx.Client(timeout=120.0)
    url = _drive_media_url(file_id)
    return client.stream("GET", url, headers={"Authorization": f"Bearer {access_token}"})
