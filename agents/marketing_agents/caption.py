"""Ensambla la descripción publicable: copy + enlace opcional + hashtags."""

from __future__ import annotations

_DEFAULT_HASHTAGS = ("#Marketing", "#Contenido", "#PowerUps")


def normalize_hashtags(tags: list[str] | None) -> list[str]:
    """Normaliza hashtags con prefijo #, sin vacíos ni duplicados (orden estable)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags or []:
        t = (raw or "").strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = f"#{t.lstrip('#')}"
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def ensure_hashtags(tags: list[str] | None, *, fallback: list[str] | None = None) -> list[str]:
    """Garantiza al menos 3 hashtags; usa fallback o defaults de marca si vienen vacíos."""
    normalized = normalize_hashtags(tags)
    if normalized:
        return normalized
    return normalize_hashtags(fallback) or list(_DEFAULT_HASHTAGS)


def build_publish_caption(
    copy_final: str,
    hashtags: list[str] | None,
    *,
    link_url: str | None = None,
) -> str:
    """Arma la descripción del post: cuerpo + link (si hay) + hashtags siempre al final.

    Los hashtags y el link viven en la caption (no como botón en la imagen).
    Evita duplicar tags/URL si el LLM ya los incluyó en el cuerpo.
    """
    body = (copy_final or "").strip()
    tags = ensure_hashtags(hashtags)
    parts: list[str] = [body] if body else []

    url = (link_url or "").strip()
    if url and url not in body:
        parts.append(url)

    body_l = body.lower()
    missing = [t for t in tags if t.lower() not in body_l]
    if missing:
        # Si faltan varios, publicamos el set completo para un bloque limpio de hashtags
        if len(missing) == len(tags):
            parts.append(" ".join(tags))
        else:
            parts.append(" ".join(missing))
    elif not any(t.lower() in body_l for t in tags):
        parts.append(" ".join(tags))

    return "\n\n".join(p for p in parts if p).strip()
