"""Render de video para Reels: Shotstack (principal, block-and-poll), JSON2Video (alt documentada), mock.

Mirror de `image_providers.py` en estructura (dispatch por settings, mock de dev, guardado a static/).
"""

from __future__ import annotations

import copy
import time
import uuid
from pathlib import Path
from typing import Any

import structlog

from .video_timeline import Timeline, to_shotstack_edit

logger = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "videos"
_INITIAL_BACKOFF_S = 5.0
_MAX_BACKOFF_S = 30.0
_LOCALHOST_BASES = (
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


def render_video(
    timeline: Timeline,
    *,
    render_provider: str | None = None,
) -> tuple[str, int, int]:
    """Devuelve (video_url, width, height) para el timeline dado."""
    from gateway.app.core.settings import get_settings

    s = get_settings()
    provider = (render_provider or s.video_provider).strip().lower()

    if provider == "shotstack" and s.shotstack_api_key:
        return _shotstack_render(timeline, s.shotstack_api_key, s.shotstack_env, s.video_max_wait_seconds)
    if provider == "shotstack" and not s.shotstack_api_key:
        logger.error("video.shotstack_missing_key")
        raise RuntimeError("video_render_failed:shotstack: missing API key")
    if provider == "json2video":
        # Alternativa documentada detrás de la misma abstracción; no implementada en v1.
        logger.warning("video.json2video_not_implemented")
        return _mock(timeline)
    return _mock(timeline)


def _publicize_url(url: str, public_base: str) -> str:
    """Sustituye localhost/127.0.0.1 por PUBLIC_IMAGE_BASE_URL para que Shotstack pueda descargar el asset."""
    base = public_base.rstrip("/")
    if not base or base in _LOCALHOST_BASES:
        return url
    for local in _LOCALHOST_BASES:
        if url.startswith(local):
            return url.replace(local, base, 1)
    return url


def _publicize_edit(edit: dict[str, Any], public_base: str) -> dict[str, Any]:
    """Reescribe src locales en el edit JSON (clips + soundtrack) hacia la URL pública."""
    public = copy.deepcopy(edit)
    timeline = public.get("timeline") or {}
    soundtrack = timeline.get("soundtrack")
    if isinstance(soundtrack, dict) and "src" in soundtrack:
        soundtrack["src"] = _publicize_url(str(soundtrack["src"]), public_base)

    for track in timeline.get("tracks") or []:
        for clip in track.get("clips") or []:
            asset = clip.get("asset")
            if isinstance(asset, dict) and "src" in asset:
                asset["src"] = _publicize_url(str(asset["src"]), public_base)
    return public


def _shotstack_error_detail(exc: Exception) -> str:
    """Incluye body de respuesta HTTP cuando Shotstack rechaza el submit (p. ej. 400)."""
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)
    body = (response.text or "").strip()
    if not body:
        return str(exc)
    # Truncar para no inundar logs con payloads enormes.
    if len(body) > 2000:
        body = body[:2000] + "…"
    return f"{exc} | body={body}"


def _shotstack_render(
    timeline: Timeline,
    api_key: str,
    env: str,
    max_wait_seconds: int,
) -> tuple[str, int, int]:
    """Submit-and-poll contra la API de Shotstack; descarga el MP4 resultante a static/videos/."""
    import httpx
    from gateway.app.core.settings import get_settings

    edit = to_shotstack_edit(timeline)
    public_base = get_settings().public_image_base_url
    edit = _publicize_edit(edit, public_base)
    base = f"https://api.shotstack.io/{env}"

    # Log de src finales (sin secrets) para diagnosticar File not found de Shotstack.
    _srcs: list[str] = []
    _tl = edit.get("timeline") or {}
    _st = _tl.get("soundtrack")
    if isinstance(_st, dict) and _st.get("src"):
        _srcs.append(str(_st["src"])[:120])
    for _tr in _tl.get("tracks") or []:
        for _cl in _tr.get("clips") or []:
            _a = _cl.get("asset")
            if isinstance(_a, dict) and _a.get("src"):
                _srcs.append(str(_a["src"])[:120])
    logger.info("video.shotstack_submit_srcs", public_base=public_base, srcs=_srcs)

    try:
        submit_resp = httpx.post(
            f"{base}/render",
            json=edit,
            headers={"x-api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )
        submit_resp.raise_for_status()
        render_id = submit_resp.json()["response"]["id"]
    except Exception as exc:
        detail = _shotstack_error_detail(exc)
        logger.error("video.shotstack_submit_error", error=detail)
        raise RuntimeError(f"video_render_failed:shotstack: {detail}") from exc

    poll_url = f"{base}/render/{render_id}"
    start = time.monotonic()
    backoff = _INITIAL_BACKOFF_S

    while True:
        try:
            poll_resp = httpx.get(
                poll_url,
                headers={"x-api-key": api_key, "Accept": "application/json"},
                timeout=30,
            )
            poll_resp.raise_for_status()
            data = poll_resp.json()["response"]
            status = data.get("status")
        except Exception as exc:
            detail = _shotstack_error_detail(exc)
            logger.error("video.shotstack_poll_error", error=detail)
            raise RuntimeError(f"video_render_failed:shotstack: {detail}") from exc

        if status == "done":
            return _download_and_store(data["url"], timeline.output.width, timeline.output.height)

        if status == "failed":
            error_detail = data.get("error") or "unknown render error"
            logger.error("video.shotstack_render_failed", detail=error_detail)
            raise RuntimeError(f"video_render_failed:shotstack: {error_detail}")

        if time.monotonic() - start > max_wait_seconds:
            logger.error("video.shotstack_poll_timeout", waited_s=max_wait_seconds)
            raise TimeoutError(f"video_render_timeout:shotstack: exceeded {max_wait_seconds}s")

        time.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF_S)


def _download_and_store(remote_url: str, width: int, height: int) -> tuple[str, int, int]:
    """Descarga el MP4 renderizado y lo persiste en static/videos/."""
    import httpx

    try:
        resp = httpx.get(remote_url, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        raw = resp.content
    except Exception as exc:
        logger.error("video.download_error", error=str(exc))
        raise RuntimeError(f"video_render_failed:download: {exc}") from exc

    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"shotstack_{uuid.uuid4().hex}.mp4"
    (_STATIC_DIR / filename).write_bytes(raw)
    url = f"http://localhost:8000/static/videos/{filename}"
    logger.info("video.shotstack_downloaded", url=url)
    return url, width, height


def _mock(timeline: Timeline) -> tuple[str, int, int]:
    """Escribe un marcador de video placeholder (sin proveedor real, para dev)."""
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"mock_{uuid.uuid4().hex}.mp4"
    (_STATIC_DIR / filename).write_bytes(b"MOCK_VIDEO_PLACEHOLDER")
    url = f"http://localhost:8000/static/videos/{filename}"
    logger.info("video.mock_generated", url=url)
    return url, timeline.output.width, timeline.output.height
