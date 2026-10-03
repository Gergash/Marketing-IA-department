"""Webhook de Meta para DMs de Instagram y Messenger.

GET  /api/webhooks/meta  → verificación de suscripción (hub.challenge)
POST /api/webhooks/meta  → eventos de mensajes firmados con X-Hub-Signature-256

Responde 200 rápido: el agente corre en Celery (handle_dm_task).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.services.dm_service import IncomingDm, record_incoming, resolve_account

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_OBJECT_TO_PLATFORM = {"instagram": "instagram", "page": "messenger"}


def _app_secret() -> str:
    s = get_settings()
    return (s.meta_client_secret or s.meta_app_secret or "").strip()


def verify_signature(raw_body: bytes, header_value: str | None, secret: str) -> bool:
    """Valida X-Hub-Signature-256 (HMAC-SHA256 del body crudo con el App Secret)."""
    if not secret or not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value.removeprefix("sha256="))


def _attachment_text(message: dict) -> str:
    kinds = [str(a.get("type") or "adjunto") for a in message.get("attachments") or []]
    return f"[envió {', '.join(kinds)}]" if kinds else ""


def parse_incoming(payload: dict) -> list[IncomingDm]:
    """Extrae los mensajes de texto/adjuntos de la persona; ignora ecos, lecturas y reacciones."""
    platform = _OBJECT_TO_PLATFORM.get(str(payload.get("object") or ""))
    if platform is None:
        return []
    items: list[IncomingDm] = []
    for entry in payload.get("entry") or []:
        for event in entry.get("messaging") or []:
            message = event.get("message") or {}
            if not message or message.get("is_echo") or message.get("is_deleted"):
                continue
            sender_id = str((event.get("sender") or {}).get("id") or "")
            recipient_id = str((event.get("recipient") or {}).get("id") or entry.get("id") or "")
            mid = str(message.get("mid") or "")
            text = (message.get("text") or "").strip() or _attachment_text(message)
            if not (sender_id and recipient_id and mid and text) or sender_id == recipient_id:
                continue
            ts = event.get("timestamp")
            sent_at = datetime.utcfromtimestamp(ts / 1000) if isinstance(ts, (int, float)) else datetime.utcnow()
            items.append(IncomingDm(
                platform=platform,
                recipient_id=recipient_id,
                sender_id=sender_id,
                mid=mid,
                text=text[:4000],
                sent_at=sent_at,
            ))
    return items


def _enqueue_agent_turn(contact_id: int, message_id: int) -> None:
    try:
        from workers.tasks import handle_dm_task

        handle_dm_task.apply_async(
            args=[contact_id, message_id],
            countdown=max(0, int(get_settings().dm_debounce_seconds)),
        )
    except Exception as exc:  # noqa: BLE001
        # Sin Redis el mensaje queda guardado y visible en la bandeja; solo no hay respuesta automática
        logger.warning("dm_webhook.enqueue_failed", contact_id=contact_id, error=str(exc))


@router.get("/meta", response_class=PlainTextResponse)
def verify_meta_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
) -> str:
    expected = (get_settings().meta_webhook_verify_token or "").strip()
    if hub_mode == "subscribe" and expected and hmac.compare_digest(hub_verify_token, expected):
        return hub_challenge
    raise HTTPException(status_code=403, detail="Verify token inválido")


@router.post("/meta")
async def receive_meta_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256"), _app_secret()):
        logger.warning("dm_webhook.bad_signature")
        raise HTTPException(status_code=403, detail="Firma inválida")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {"ok": True, "received": 0}

    received = 0
    for incoming in parse_incoming(payload):
        account = resolve_account(db, incoming)
        if account is None:
            logger.info("dm_webhook.unknown_recipient", platform=incoming.platform, recipient_id=incoming.recipient_id)
            continue
        message = record_incoming(db, account, incoming)
        if message is None:
            continue
        received += 1
        if account.dm_agent_enabled:
            _enqueue_agent_turn(message.contact_id, message.id)
    return {"ok": True, "received": received}
