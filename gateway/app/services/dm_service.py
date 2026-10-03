"""Bandeja de DMs (Instagram / Messenger): registro de mensajes, turno del agente y respuestas manuales."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gateway.app.core.settings import get_settings
from gateway.app.models import DmContact, DmMessage, OAuthToken

logger = structlog.get_logger(__name__)

PLATFORMS = ("instagram", "messenger")
STATUSES = ("nuevo", "en_conversacion", "datos_completos", "requiere_humano", "cerrado")
MOTIVE_CATEGORIES = ("compra", "cotizacion", "soporte", "queja", "colaboracion", "informacion", "otro")
# Estados en los que el agente ya no contesta solo
_AGENT_SILENT_STATUSES = ("requiere_humano", "cerrado")
# Política de Meta: fuera de 24 h desde el último mensaje de la persona no se puede responder libremente
MESSAGING_WINDOW = timedelta(hours=24)
_HISTORY_LIMIT = 30


@dataclass
class IncomingDm:
    """Mensaje entrante ya normalizado desde el payload del webhook."""

    platform: str  # instagram | messenger
    recipient_id: str  # IG account id o Page id que recibió el DM
    sender_id: str
    mid: str
    text: str
    sent_at: datetime


def resolve_account(db: Session, incoming: IncomingDm) -> OAuthToken | None:
    """Cuenta conectada que recibió el DM: IG por account_id, Messenger por page_id."""
    column = OAuthToken.account_id if incoming.platform == "instagram" else OAuthToken.page_id
    return db.execute(
        select(OAuthToken)
        .where(
            OAuthToken.provider == "meta",
            OAuthToken.is_active.is_(True),
            column == incoming.recipient_id,
        )
        .order_by(OAuthToken.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def record_incoming(db: Session, account: OAuthToken, incoming: IncomingDm) -> DmMessage | None:
    """Guarda el mensaje entrante (y el contacto si es nuevo). None si el mid ya estaba registrado."""
    if db.execute(select(DmMessage.id).where(DmMessage.meta_mid == incoming.mid)).first():
        return None

    contact = db.execute(
        select(DmContact).where(
            DmContact.tenant_id == account.tenant_id,
            DmContact.platform == incoming.platform,
            DmContact.sender_id == incoming.sender_id,
        )
    ).scalar_one_or_none()
    if contact is None:
        contact = DmContact(
            tenant_id=account.tenant_id,
            oauth_token_id=account.id,
            platform=incoming.platform,
            sender_id=incoming.sender_id,
            status="nuevo",
            created_at=incoming.sent_at,
        )
        db.add(contact)
        db.flush()
    elif contact.status == "cerrado":
        # Vuelve a escribir tras cerrarse: se reabre la conversación
        contact.status = "en_conversacion"
    contact.oauth_token_id = account.id
    contact.last_message_at = incoming.sent_at

    message = DmMessage(
        contact_id=contact.id,
        direction="in",
        sent_by="contact",
        text=incoming.text,
        meta_mid=incoming.mid,
        created_at=incoming.sent_at,
    )
    db.add(message)
    try:
        db.commit()
    except IntegrityError:
        # Reintento concurrente de Meta con el mismo mid
        db.rollback()
        return None
    db.refresh(message)
    return message


def history_for(db: Session, contact_id: int, limit: int = _HISTORY_LIMIT) -> list[DmMessage]:
    """Últimos mensajes de la conversación en orden cronológico."""
    rows = db.execute(
        select(DmMessage)
        .where(DmMessage.contact_id == contact_id)
        .order_by(DmMessage.created_at.desc(), DmMessage.id.desc())
        .limit(limit)
    ).scalars().all()
    return list(reversed(rows))


def last_incoming_at(db: Session, contact_id: int) -> datetime | None:
    row = db.execute(
        select(DmMessage.created_at)
        .where(DmMessage.contact_id == contact_id, DmMessage.direction == "in")
        .order_by(DmMessage.created_at.desc())
        .limit(1)
    ).first()
    return row[0] if row else None


def within_messaging_window(db: Session, contact_id: int, now: datetime | None = None) -> bool:
    last_in = last_incoming_at(db, contact_id)
    if last_in is None:
        return False
    return (now or datetime.utcnow()) - last_in <= MESSAGING_WINDOW


def _has_newer_incoming(db: Session, contact_id: int, trigger_message_id: int) -> bool:
    """Debounce: si llegó otro mensaje después del que disparó la tarea, esa otra tarea responde."""
    return db.execute(
        select(DmMessage.id).where(
            DmMessage.contact_id == contact_id,
            DmMessage.direction == "in",
            DmMessage.id > trigger_message_id,
        ).limit(1)
    ).first() is not None


def agent_should_reply(account: OAuthToken | None, contact: DmContact) -> tuple[bool, str]:
    """Reglas de silencio del agente. Devuelve (responder, motivo_si_no)."""
    if account is None or not account.is_active:
        return False, "account_inactive"
    if not account.dm_agent_enabled:
        return False, "agent_disabled"
    if contact.bot_paused:
        return False, "bot_paused"
    if contact.status in _AGENT_SILENT_STATUSES:
        return False, f"status_{contact.status}"
    return True, ""


def _clean(value: object, max_len: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value.lower() in ("null", "none", "n/a", "desconocido"):
        return None
    return value[:max_len]


def merge_agent_result(contact: DmContact, result: dict) -> None:
    """Fusiona lo que extrajo el agente sin pisar datos ya capturados con valores vacíos."""
    for field, max_len in (("full_name", 256), ("phone", 64), ("city", 128)):
        value = _clean(result.get(field), max_len)
        if value:
            setattr(contact, field, value)

    motive = _clean(result.get("motive"), 2000)
    if motive:
        contact.motive = motive
    category = _clean(result.get("motive_category"), 32)
    if category:
        category = category.lower()
        contact.motive_category = category if category in MOTIVE_CATEGORIES else "otro"
    summary = _clean(result.get("summary"), 2000)
    if summary:
        contact.summary = summary
    if result.get("privacy_notice_included"):
        contact.privacy_notice_sent = True

    if result.get("needs_human"):
        contact.status = "requiere_humano"
    elif contact.full_name and contact.phone and contact.city:
        contact.status = "datos_completos"
    else:
        contact.status = "en_conversacion"


def _brand_context(tenant_id: str) -> str:
    try:
        from agents.marketing_agents.brand_manual import load_brand_text

        return load_brand_text(tenant_id, max_chars=4000)
    except Exception:  # noqa: BLE001
        return ""


def _typing_pause_seconds(text: str) -> float:
    """Pausa proporcional al largo de la respuesta para que no parezca instantánea (tope 4 s)."""
    base = max(0.0, float(get_settings().dm_agent_reply_delay_seconds))
    return min(4.0, base + len(text) / 80.0) if base else 0.0


def handle_agent_turn(db: Session, contact_id: int, trigger_message_id: int) -> str:
    """Ejecuta un turno del agente para la conversación. Devuelve el resultado para logs/tests."""
    from agents.marketing_agents.dm_responder import DmResponderAgent
    from agents.marketing_agents.dm_sender import DmSendError, fetch_profile_name, send_text, send_typing

    contact = db.get(DmContact, contact_id)
    if contact is None:
        return "contact_missing"
    if _has_newer_incoming(db, contact_id, trigger_message_id):
        return "debounced"

    account = db.get(OAuthToken, contact.oauth_token_id) if contact.oauth_token_id else None
    should_reply, reason = agent_should_reply(account, contact)
    if not should_reply:
        logger.info("dm_agent.skip", contact_id=contact_id, reason=reason)
        return reason

    s = get_settings()
    if not contact.display_name and not s.dm_agent_dry_run:
        contact.display_name = fetch_profile_name(
            account.access_token, contact.platform, contact.sender_id, graph_version=s.graph_api_version
        )

    history = [
        {"role": "persona" if m.direction == "in" else "marca", "text": m.text}
        for m in history_for(db, contact_id)
    ]
    result = DmResponderAgent().run(
        history,
        {
            "display_name": contact.display_name,
            "full_name": contact.full_name,
            "phone": contact.phone,
            "city": contact.city,
            "motive": contact.motive,
            "privacy_notice_sent": contact.privacy_notice_sent,
        },
        brand_name=account.account_name or "la marca",
        brand_context=_brand_context(contact.tenant_id),
        privacy_url=s.dm_privacy_url,
    )

    if result.get("llm_error"):
        contact.status = "requiere_humano"
        contact.summary = contact.summary or "El asistente no pudo generar respuesta; revisa la conversación."
        db.commit()
        return "llm_error"

    # La persona pudo escribir otra vez mientras el LLM pensaba: la tarea de ese mensaje responde
    if _has_newer_incoming(db, contact_id, trigger_message_id):
        db.rollback()
        return "debounced"

    merge_agent_result(contact, result)
    reply = (result.get("reply") or "").strip()
    if not reply:
        db.commit()
        return "no_reply"

    if s.dm_agent_dry_run:
        mid = None
    else:
        send_typing(account.access_token, contact.sender_id, graph_version=s.graph_api_version)
        pause = _typing_pause_seconds(reply)
        if pause:
            time.sleep(pause)
        try:
            mid = send_text(account.access_token, contact.sender_id, reply, graph_version=s.graph_api_version)
        except DmSendError as exc:
            logger.warning("dm_agent.send_failed", contact_id=contact_id, error=str(exc))
            contact.status = "requiere_humano"
            db.commit()
            return "send_failed"

    now = datetime.utcnow()
    db.add(DmMessage(contact_id=contact.id, direction="out", sent_by="agent", text=reply, meta_mid=mid, created_at=now))
    contact.last_message_at = now
    db.commit()
    return "replied"


def send_manual_reply(db: Session, contact: DmContact, text: str) -> DmMessage:
    """Respuesta escrita por una persona del equipo: pausa al agente en esta conversación."""
    from agents.marketing_agents.dm_sender import send_text

    account = db.get(OAuthToken, contact.oauth_token_id) if contact.oauth_token_id else None
    if account is None or not account.is_active:
        raise ValueError("La cuenta conectada de esta conversación ya no está activa.")
    if not within_messaging_window(db, contact.id):
        raise PermissionError("Pasaron más de 24 h desde el último mensaje de la persona; Meta no permite responder.")

    s = get_settings()
    mid = None if s.dm_agent_dry_run else send_text(
        account.access_token, contact.sender_id, text, graph_version=s.graph_api_version
    )
    now = datetime.utcnow()
    message = DmMessage(contact_id=contact.id, direction="out", sent_by="human", text=text, meta_mid=mid, created_at=now)
    db.add(message)
    contact.bot_paused = True
    contact.last_message_at = now
    if contact.status == "nuevo":
        contact.status = "en_conversacion"
    db.commit()
    db.refresh(message)
    return message


def contacts_query(
    tenant_id: str,
    *,
    account_id: int | None = None,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
):
    """SELECT de contactos del tenant con los filtros del panel."""
    stmt = select(DmContact).where(DmContact.tenant_id == tenant_id)
    if account_id is not None:
        stmt = stmt.where(DmContact.oauth_token_id == account_id)
    if status:
        stmt = stmt.where(DmContact.status == status)
    if category:
        stmt = stmt.where(DmContact.motive_category == category)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(
            DmContact.full_name.ilike(like),
            DmContact.display_name.ilike(like),
            DmContact.phone.ilike(like),
            DmContact.city.ilike(like),
            DmContact.motive.ilike(like),
        ))
    return stmt.order_by(DmContact.last_message_at.desc().nullslast(), DmContact.id.desc())
