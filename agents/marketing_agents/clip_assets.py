"""Referencia/almacenamiento de clips de video descargados (sin acoplamiento a PIL/imagen).

Mirror minimal de `user_assets.py` pero para video: solo resuelve URLs servibles desde
rutas absolutas bajo static/uploads/clips/, sin tocar bytes ni requerir Pillow.
"""

from __future__ import annotations

from pathlib import Path

_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"


def clip_public_url(local_path: str) -> str:
    """Convierte una ruta absoluta bajo static/ en la URL servida por FastAPI.

    Si la ruta no cuelga de static/ (caso inesperado), la devuelve tal cual.
    """
    path = Path(local_path)
    try:
        rel = path.resolve().relative_to(_STATIC_ROOT.resolve())
    except ValueError:
        return local_path
    return f"http://localhost:8000/static/{rel.as_posix()}"
