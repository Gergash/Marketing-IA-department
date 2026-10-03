"""Bandeja de DMs del estudio: quién escribe a las cuentas conectadas, con qué motivo, y control del agente."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gateway.app.core.auth import require_auth
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models import DmContact, OAuthToken
from gateway.app.services.dm_service import (
    MOTIVE_CATEGORIES,
    STATUSES,
    contacts_query,
    history_for,
    send_manual_reply,
    within_messaging_window,
)

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class ContactPatch(BaseModel):
    bot_paused: bool | None = None
    status: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    full_name: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=128)
    motive_category: str | None = None


class ReplyBody(BaseModel):
    text: str = Field(min_length=1, max_length=900)


class AccountPatch(BaseModel):
    dm_agent_enabled: bool


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _contact_dict(c: DmContact, account_names: dict[int, str | None]) -> dict:
    return {
        "id": c.id,
        "platform": c.platform,
        "account_id": c.oauth_token_id,
        "account_name": account_names.get(c.oauth_token_id) if c.oauth_token_id else None,
        "display_name": c.display_name,
        "full_name": c.full_name,
        "phone": c.phone,
        "city": c.city,
        "motive": c.motive,
        "motive_category": c.motive_category,
        "status": c.status,
        "bot_paused": c.bot_paused,
        "summary": c.summary,
        "notes": c.notes,
        "last_message_at": _iso(c.last_message_at),
        "created_at": _iso(c.created_at),
    }


def _account_names(db: Session, tenant_id: str) -> dict[int, str | None]:
    rows = db.execute(
        select(OAuthToken.id, OAuthToken.account_name).where(OAuthToken.tenant_id == tenant_id)
    ).all()
    return {row.id: row.account_name for row in rows}


def _get_contact(db: Session, tenant_id: str, contact_id: int) -> DmContact:
    contact = db.get(DmContact, contact_id)
    if contact is None or contact.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return contact


def _validate_filters(status: str | None, category: str | None) -> None:
    if status and status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status debe ser uno de {', '.join(STATUSES)}")
    if category and category not in MOTIVE_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category debe ser una de {', '.join(MOTIVE_CATEGORIES)}")


@router.get("/accounts")
def list_inbox_accounts(tenant_id: str = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    """Cuentas Meta conectadas con el estado del agente y conteo de conversaciones."""
    accounts = db.execute(
        select(OAuthToken)
        .where(OAuthToken.tenant_id == tenant_id, OAuthToken.provider == "meta", OAuthToken.is_active.is_(True))
        .order_by(OAuthToken.id)
    ).scalars().all()
    counts = dict(db.execute(
        select(DmContact.oauth_token_id, func.count(DmContact.id))
        .where(DmContact.tenant_id == tenant_id)
        .group_by(DmContact.oauth_token_id)
    ).all())
    return {
        "items": [
            {
                "id": a.id,
                "account_name": a.account_name,
                "profile_picture_url": a.profile_picture_url,
                "has_page": bool(a.page_id),
                "dm_agent_enabled": a.dm_agent_enabled,
                "contacts": counts.get(a.id, 0),
            }
            for a in accounts
        ],
    }


@router.patch("/accounts/{oauth_token_id}")
def toggle_dm_agent(
    oauth_token_id: int,
    body: AccountPatch,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    account = db.get(OAuthToken, oauth_token_id)
    if account is None or account.tenant_id != tenant_id or account.provider != "meta" or not account.is_active:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    account.dm_agent_enabled = body.dm_agent_enabled
    db.commit()
    subscribed = None
    if body.dm_agent_enabled and account.page_id:
        # Cuentas conectadas antes del agente no estaban suscritas al webhook de mensajes
        from agents.marketing_agents.dm_sender import subscribe_page_to_messages

        subscribed = subscribe_page_to_messages(
            account.page_id, account.access_token, graph_version=get_settings().graph_api_version
        )
    return {"id": account.id, "dm_agent_enabled": account.dm_agent_enabled, "webhook_subscribed": subscribed}


@router.get("/contacts")
def list_contacts(
    account_id: int | None = None,
    status: str | None = None,
    category: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    _validate_filters(status, category)
    stmt = contacts_query(tenant_id, account_id=account_id, status=status, category=category, search=q)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    by_status = dict(db.execute(
        select(DmContact.status, func.count(DmContact.id))
        .where(DmContact.tenant_id == tenant_id)
        .group_by(DmContact.status)
    ).all())
    names = _account_names(db, tenant_id)
    return {
        "items": [_contact_dict(c, names) for c in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "counts_by_status": by_status,
    }


_CSV_COLUMNS = (
    ("full_name", "Nombre"),
    ("display_name", "Perfil"),
    ("phone", "Teléfono"),
    ("city", "Ciudad/Barrio"),
    ("motive_category", "Categoría"),
    ("motive", "Motivo"),
    ("status", "Estado"),
    ("platform", "Red"),
    ("account_name", "Cuenta"),
    ("last_message_at", "Último mensaje"),
    ("notes", "Notas"),
)


@router.get("/contacts.csv")
def export_contacts_csv(
    account_id: int | None = None,
    status: str | None = None,
    category: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _validate_filters(status, category)
    rows = db.execute(
        contacts_query(tenant_id, account_id=account_id, status=status, category=category, search=q)
    ).scalars().all()
    names = _account_names(db, tenant_id)
    buf = io.StringIO()
    # BOM: Excel abre el CSV con tildes correctas
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow([label for _, label in _CSV_COLUMNS])
    for c in rows:
        data = _contact_dict(c, names)
        writer.writerow([data.get(key) or "" for key, _ in _CSV_COLUMNS])
    filename = f"contactos-dm-{datetime.utcnow():%Y%m%d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/contacts/{contact_id}")
def get_contact(contact_id: int, tenant_id: str = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    contact = _get_contact(db, tenant_id, contact_id)
    data = _contact_dict(contact, _account_names(db, tenant_id))
    data["can_reply"] = within_messaging_window(db, contact.id)
    data["messages"] = [
        {
            "id": m.id,
            "direction": m.direction,
            "sent_by": m.sent_by,
            "text": m.text,
            "created_at": _iso(m.created_at),
        }
        for m in history_for(db, contact.id, limit=200)
    ]
    return data


@router.patch("/contacts/{contact_id}")
def update_contact(
    contact_id: int,
    body: ContactPatch,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    contact = _get_contact(db, tenant_id, contact_id)
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status debe ser uno de {', '.join(STATUSES)}")
    if "motive_category" in changes and changes["motive_category"] not in MOTIVE_CATEGORIES:
        raise HTTPException(status_code=422, detail="Categoría de motivo inválida")
    for field, value in changes.items():
        setattr(contact, field, value.strip() if isinstance(value, str) else value)
    # Reanudar el agente saca la conversación de "requiere_humano" para que vuelva a contestar
    if changes.get("bot_paused") is False and "status" not in changes and contact.status == "requiere_humano":
        contact.status = "en_conversacion"
    db.commit()
    return _contact_dict(contact, _account_names(db, tenant_id))


@router.post("/contacts/{contact_id}/reply")
def reply_to_contact(
    contact_id: int,
    body: ReplyBody,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    from agents.marketing_agents.dm_sender import DmSendError

    contact = _get_contact(db, tenant_id, contact_id)
    try:
        message = send_manual_reply(db, contact, body.text.strip())
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DmSendError as exc:
        raise HTTPException(status_code=502, detail=f"Meta rechazó el mensaje: {exc}") from exc
    return {
        "id": message.id,
        "direction": message.direction,
        "sent_by": message.sent_by,
        "text": message.text,
        "created_at": _iso(message.created_at),
        "bot_paused": contact.bot_paused,
    }
