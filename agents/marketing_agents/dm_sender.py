"""Envío de DMs por Graph API (Instagram y Messenger comparten el endpoint /me/messages con el Page token)."""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger(__name__)

_TIMEOUT = 15


class DmSendError(RuntimeError):
    """Meta rechazó el envío (token caducado, fuera de la ventana de 24 h, permisos, etc.)."""


def _base(graph_version: str) -> str:
    return f"https://graph.facebook.com/{(graph_version or 'v21.0').strip().lstrip('/')}"


def _graph_error(response: httpx.Response) -> str:
    try:
        err = response.json().get("error") or {}
        return f"{response.status_code} {err.get('code', '')}: {err.get('message', response.text[:200])}"
    except ValueError:
        return f"{response.status_code}: {response.text[:200]}"


def send_text(page_token: str, recipient_id: str, text: str, *, graph_version: str = "v21.0") -> str | None:
    """Envía un mensaje de texto como respuesta (messaging_type RESPONSE). Devuelve el message_id de Meta."""
    try:
        r = httpx.post(
            f"{_base(graph_version)}/me/messages",
            params={"access_token": page_token},
            json={
                "recipient": {"id": recipient_id},
                "messaging_type": "RESPONSE",
                "message": {"text": text},
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise DmSendError(f"Error de red al enviar el DM: {exc}") from exc
    if not r.is_success:
        raise DmSendError(_graph_error(r))
    return r.json().get("message_id")


def send_typing(page_token: str, recipient_id: str, *, graph_version: str = "v21.0") -> None:
    """Muestra "escribiendo…" (best effort: un fallo aquí no bloquea la respuesta)."""
    try:
        httpx.post(
            f"{_base(graph_version)}/me/messages",
            params={"access_token": page_token},
            json={"recipient": {"id": recipient_id}, "sender_action": "typing_on"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        logger.debug("dm_sender.typing_failed", error=str(exc))


def fetch_profile_name(page_token: str, platform: str, sender_id: str, *, graph_version: str = "v21.0") -> str | None:
    """Nombre visible de la persona (IG: name/username; Messenger: first/last name). None si Meta no lo da."""
    fields = "name,username" if platform == "instagram" else "first_name,last_name"
    try:
        r = httpx.get(
            f"{_base(graph_version)}/{sender_id}",
            params={"fields": fields, "access_token": page_token},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        return None
    if not r.is_success:
        return None
    data = r.json()
    if platform == "instagram":
        name = data.get("name") or (f"@{data['username']}" if data.get("username") else None)
    else:
        name = " ".join(p for p in (data.get("first_name"), data.get("last_name")) if p) or None
    return name[:256] if name else None


def subscribe_page_to_messages(page_id: str, page_token: str, *, graph_version: str = "v21.0") -> bool:
    """Suscribe la app a los eventos de mensajes de la página (necesario para recibir el webhook)."""
    try:
        r = httpx.post(
            f"{_base(graph_version)}/{page_id}/subscribed_apps",
            params={
                "subscribed_fields": "messages,messaging_postbacks",
                "access_token": page_token,
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        logger.warning("dm_sender.subscribe_failed", page_id=page_id, error=str(exc))
        return False
    if not r.is_success:
        logger.warning("dm_sender.subscribe_failed", page_id=page_id, error=_graph_error(r))
        return False
    return bool(r.json().get("success", True))
