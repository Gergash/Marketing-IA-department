"""Integración con Google Drive: refresh de token headless, listado y descarga de clips de video.

Todo el I/O de red (Google OAuth token endpoint, Drive API) vive en funciones de módulo
reemplazables por monkeypatch en tests — nunca se ejecuta red real en tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.settings import get_settings
from gateway.app.models import OAuthToken

logger = structlog.get_logger(__name__)

_STATIC_CLIPS_DIR = Path(__file__).resolve().parents[2] / "static" / "uploads" / "clips"


class DriveAuthError(RuntimeError):
    """Token de Google Drive ausente, expirado o revocado — el usuario debe reconectar."""


class DownloadedClip(BaseModel):
    """Clip de video descargado localmente desde Drive."""

    clip_id: str
    path: str
    filename: str


def _get_token_row(db: Session, tenant_id: str) -> OAuthToken:
    """Lee el token de Google Drive del tenant; None → nunca se conectó (reconectar)."""
    token = db.execute(
        select(OAuthToken).where(OAuthToken.tenant_id == tenant_id, OAuthToken.provider == "google")
    ).scalar_one_or_none()
    if token is None:
        raise DriveAuthError("No hay cuenta de Google Drive conectada. Reconecta Google Drive.")
    return token


def _refresh_access_token(db: Session, token: OAuthToken) -> str:
    """Refresca el access_token si expiró usando el refresh_token guardado (headless, Celery-safe)."""
    if token.expires_at and token.expires_at > datetime.utcnow():
        return token.access_token

    if not token.refresh_token:
        raise DriveAuthError("El token de Google Drive no tiene refresh_token. Reconecta Google Drive.")

    s = get_settings()
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": s.google_client_id,
                    "client_secret": s.google_client_secret,
                    "refresh_token": token.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        # No reintento silencioso: Google rechazó el refresh, el usuario debe reconectar
        logger.error("drive.token_refresh_failed", error=str(exc))
        raise DriveAuthError("Google rechazó el refresh del token. Reconecta Google Drive.") from exc

    token.access_token = data["access_token"]
    token.expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
    db.commit()
    return token.access_token


def _list_folder_files(access_token: str, folder_id: str) -> list[dict]:
    """Lista archivos (no-trashed) de una carpeta de Drive vía Drive API v3."""
    with httpx.Client(timeout=15) as client:
        r = client.get(
            "https://www.googleapis.com/drive/v3/files",
            params={
                "q": f"'{folder_id}' in parents and trashed=false",
                "fields": "files(id,name,mimeType)",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        return r.json().get("files", [])


def _download_file(access_token: str, file_id: str, dest_path: Path) -> None:
    """Descarga el contenido binario de un archivo de Drive a disco."""
    with httpx.Client(timeout=60) as client:
        r = client.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"alt": "media"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        dest_path.write_bytes(r.content)


def list_and_download_clips(
    db: Session,
    tenant_id: str,
    folder_id: str,
    run_id: int,
) -> list[DownloadedClip]:
    """Lista los videos de la carpeta de Drive y los descarga a static/uploads/clips/{run_id}/."""
    token_row = _get_token_row(db, tenant_id)
    access_token = _refresh_access_token(db, token_row)

    files = _list_folder_files(access_token, folder_id)
    if not files:
        raise RuntimeError("no_clips_found: la carpeta de Drive está vacía")

    video_files = [f for f in files if (f.get("mimeType") or "").startswith("video/")]
    if not video_files:
        raise RuntimeError("no_clips_found: la carpeta no contiene archivos de video")

    dest_dir = _STATIC_CLIPS_DIR / str(run_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[DownloadedClip] = []
    for f in video_files:
        clip_id = uuid.uuid4().hex
        raw_name = f.get("name") or f"{clip_id}.mp4"
        # Path(...).name descarta cualquier componente de directorio (../, rutas absolutas) del nombre
        # que Drive devuelve sin sanitizar, evitando path traversal al construir dest_path.
        safe_name = Path(raw_name).name or f"{clip_id}.mp4"
        # Prefijo con el id de archivo de Drive: nombres duplicados en la carpeta ya no se pisan entre si.
        filename = f"{f['id']}_{safe_name}"
        dest_path = dest_dir / filename
        _download_file(access_token, f["id"], dest_path)
        downloaded.append(DownloadedClip(clip_id=clip_id, path=str(dest_path), filename=filename))

    return downloaded
