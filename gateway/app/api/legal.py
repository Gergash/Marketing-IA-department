"""Páginas legales públicas (TikTok / App Review): mismos paths en el dominio ngrok."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["legal"])

_LEGAL_DIR = Path(__file__).resolve().parents[3] / "static" / "legal"


def _legal_file(name: str) -> Path:
    path = _LEGAL_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"legal file missing: {name}")
    return path


@router.get("/terminos", response_class=HTMLResponse, include_in_schema=False)
def terminos_de_servicio() -> FileResponse:
    """Condiciones de Servicio — URL pública HTML para TikTok Developers."""
    return FileResponse(
        _legal_file("terminos.html"),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/privacidad", response_class=HTMLResponse, include_in_schema=False)
def politica_de_privacidad() -> FileResponse:
    """Política de Privacidad — URL pública HTML para TikTok Developers."""
    return FileResponse(
        _legal_file("privacidad.html"),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/terminos.pdf", include_in_schema=False)
def terminos_pdf() -> FileResponse:
    return FileResponse(
        _legal_file("terminos.pdf"),
        media_type="application/pdf",
        filename="Condiciones-de-servicio-Marketing-DEPA-IA.pdf",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/privacidad.pdf", include_in_schema=False)
def privacidad_pdf() -> FileResponse:
    return FileResponse(
        _legal_file("privacidad.pdf"),
        media_type="application/pdf",
        filename="Politicas-de-privacidad-Marketing-DEPA-IA.pdf",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/terms", include_in_schema=False)
@router.get("/terms-of-service", include_in_schema=False)
def terms_alias() -> FileResponse:
    return terminos_de_servicio()


@router.get("/privacy", include_in_schema=False)
@router.get("/privacy-policy", include_in_schema=False)
def privacy_alias() -> FileResponse:
    return politica_de_privacidad()
