"""Referencia/almacenamiento de clips de video descargados (sin acoplamiento a PIL/imagen).

Mirror minimal de `user_assets.py` pero para video: solo resuelve URLs servibles desde
rutas absolutas bajo static/uploads/clips/, sin tocar bytes ni requerir Pillow.
"""

from __future__ import annotations

from pathlib import Path

_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"


def clip_public_url(local_path: str) -> str:
    """Convierte una ruta absoluta bajo static/ en la URL servida por FastAPI.

    Usa `PUBLIC_IMAGE_BASE_URL` en vez de localhost porque fal.ai wan-effects descarga
    el clip fuente a mitad de pipeline: con localhost el efecto falla y el reel degrada
    al segmento sin procesar. Shotstack ya normalizaba por su cuenta en `_publicize_edit`.

    Si la ruta no cuelga de static/ (caso inesperado), la devuelve tal cual.
    """
    from gateway.app.core.settings import get_settings

    path = Path(local_path)
    try:
        rel = path.resolve().relative_to(_STATIC_ROOT.resolve())
    except ValueError:
        return local_path
    base = get_settings().public_image_base_url.rstrip("/")
    return f"{base}/static/{rel.as_posix()}"
