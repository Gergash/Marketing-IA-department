"""Verificación de dominio TikTok (archivo .txt en la raíz del dominio ngrok → :8000)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from gateway.app.core.settings import get_settings

router = APIRouter(tags=["tiktok-verify"])

_VERIFY_DIR = Path(__file__).resolve().parents[3] / "static" / "tiktok-verify"
_SAFE_NAME = re.compile(r"^tiktok[-A-Za-z0-9_.]+\.txt$", re.IGNORECASE)


def _content_for(filename: str) -> str | None:
    """Prioridad: archivo en static/tiktok-verify/ → variables TIKTOK_VERIFY_* del .env."""
    _VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    disk = _VERIFY_DIR / filename
    if disk.is_file():
        return disk.read_text(encoding="utf-8").strip() + "\n"

    s = get_settings()
    configured = (s.tiktok_verify_filename or "").strip()
    body = (s.tiktok_verify_content or "").strip()
    if configured and body and configured.lower() == filename.lower():
        return body + "\n"
    return None


@router.get("/{filename}", response_class=PlainTextResponse, include_in_schema=False)
def tiktok_domain_verify_file(filename: str) -> PlainTextResponse:
    """Sirve el .txt de verificación TikTok en la raíz (mismo host que ngrok).

    Ejemplo portal: archivo ``tiktokABC123.txt`` con cuerpo ``tiktokABC123``.
    Configura ``TIKTOK_VERIFY_FILENAME`` + ``TIKTOK_VERIFY_CONTENT`` o deja el
    archivo en ``static/tiktok-verify/``.
    """
    if not _SAFE_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Not Found")
    content = _content_for(filename)
    if content is None:
        raise HTTPException(status_code=404, detail="TikTok verify file not configured")
    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
