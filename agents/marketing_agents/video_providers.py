"""Render de video para Reels: Shotstack (principal, block-and-poll), JSON2Video (alt documentada), mock.

Mirror de `image_providers.py` en estructura (dispatch por settings, mock de dev, guardado a static/).
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import structlog

from .video_timeline import Timeline, to_shotstack_edit

logger = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "videos"
_INITIAL_BACKOFF_S = 5.0
_MAX_BACKOFF_S = 30.0


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


def _shotstack_render(
    timeline: Timeline,
    api_key: str,
    env: str,
    max_wait_seconds: int,
) -> tuple[str, int, int]:
    """Submit-and-poll contra la API de Shotstack; descarga el MP4 resultante a static/videos/."""
    import httpx

    edit = to_shotstack_edit(timeline)
    base = f"https://api.shotstack.io/{env}"

    try:
        submit_resp = httpx.post(
            f"{base}/render",
            json=edit,
            headers={"x-api-key": api_key},
            timeout=30,
        )
        submit_resp.raise_for_status()
        render_id = submit_resp.json()["response"]["id"]
    except Exception as exc:
        logger.error("video.shotstack_submit_error", error=str(exc))
        raise RuntimeError(f"video_render_failed:shotstack: {exc}") from exc

    poll_url = f"{base}/render/{render_id}"
    start = time.monotonic()
    backoff = _INITIAL_BACKOFF_S

    while True:
        try:
            poll_resp = httpx.get(poll_url, headers={"x-api-key": api_key}, timeout=30)
            poll_resp.raise_for_status()
            data = poll_resp.json()["response"]
            status = data.get("status")
        except Exception as exc:
            logger.error("video.shotstack_poll_error", error=str(exc))
            raise RuntimeError(f"video_render_failed:shotstack: {exc}") from exc

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
