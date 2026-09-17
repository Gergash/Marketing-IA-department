"""Panel de administrador: overview de negocio, usuarios, pagos y uso de proveedores.

Regla de seguridad innegociable: ningún endpoint expone `password_hash` ni contraseñas
en claro. El único campo relacionado servido es `password_algo` (prefijo del hash,
p.ej. "pbkdf2_sha256"), derivado sin tocar salt/digest. La vía de soporte para un
usuario bloqueado es `POST /users/{id}/reset-password`.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gateway.app.core.auth import require_admin
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models.entities import (
    AgentRun,
    ApiUsageEvent,
    AppUser,
    CreditWallet,
    PaymentRecord,
)
from gateway.app.services.auth_users import _hash_password
from gateway.app.services.credits_service import get_or_create_wallet
from gateway.app.services.usage_service import record_usage, usage_by_provider

router = APIRouter(prefix="/api/admin", tags=["admin"])
_log = structlog.get_logger(__name__)

# Proveedor sintético para ajustes manuales de crédito; se excluye del mix
# de proveedores externos (venice/fal/...) que muestra el panel.
_ADMIN_PROVIDER = "admin"


def _ensure_enabled() -> None:
    if not get_settings().admin_panel_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panel de administrador inactivo.")


def _password_algo(password_hash: str) -> str:
    return (password_hash or "").split("$", 1)[0] or "desconocido"


def _user_metrics(db: Session, tenant_id: str) -> dict:
    wallet = get_or_create_wallet(db, tenant_id)
    credits_consumed = int(
        db.execute(
            select(func.coalesce(func.sum(ApiUsageEvent.credits_cost), 0)).where(
                ApiUsageEvent.tenant_id == tenant_id,
                ApiUsageEvent.provider != _ADMIN_PROVIDER,
                ApiUsageEvent.credits_cost > 0,
            )
        ).scalar_one()
        or 0
    )
    runs_total = int(
        db.execute(select(func.count(AgentRun.id)).where(AgentRun.tenant_id == tenant_id)).scalar_one() or 0
    )
    paid_total_cop = int(
        db.execute(
            select(func.coalesce(func.sum(PaymentRecord.amount_cop), 0)).where(
                PaymentRecord.tenant_id == tenant_id,
                PaymentRecord.status == "paid",
            )
        ).scalar_one()
        or 0
    )
    last_payment_at = db.execute(
        select(func.max(PaymentRecord.created_at)).where(
            PaymentRecord.tenant_id == tenant_id,
            PaymentRecord.status == "paid",
        )
    ).scalar_one()
    return {
        "credits_balance": wallet.balance,
        "credits_consumed": credits_consumed,
        "runs_total": runs_total,
        "paid_total_cop": paid_total_cop,
        "last_payment_at": last_payment_at,
    }


def _user_item(db: Session, user: AppUser) -> dict:
    metrics = _user_metrics(db, user.tenant_id)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name or "",
        "tenant_id": user.tenant_id,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "password_algo": _password_algo(user.password_hash),
        **metrics,
    }


class UserUpdateRequest(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class CreditAdjustRequest(BaseModel):
    delta: int
    reason: str = ""


class ResetPasswordResponse(BaseModel):
    temporary_password: str
    note: str


@router.get("/overview")
def admin_overview(
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    now = datetime.utcnow()
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    users_total = int(db.execute(select(func.count(AppUser.id))).scalar_one() or 0)
    users_registered_7d = int(
        db.execute(select(func.count(AppUser.id)).where(AppUser.created_at >= since_7d)).scalar_one() or 0
    )
    users_registered_30d = int(
        db.execute(select(func.count(AppUser.id)).where(AppUser.created_at >= since_30d)).scalar_one() or 0
    )

    active_by_login = {
        r
        for r in db.execute(
            select(AppUser.tenant_id).where(AppUser.last_login_at >= since_30d)
        ).scalars()
    }
    active_by_usage = {
        r
        for r in db.execute(
            select(ApiUsageEvent.tenant_id).where(ApiUsageEvent.created_at >= since_30d).distinct()
        ).scalars()
    }
    active_by_runs = {
        r
        for r in db.execute(
            select(AgentRun.tenant_id).where(AgentRun.created_at >= since_30d).distinct()
        ).scalars()
    }
    users_active_30d = len(active_by_login | active_by_usage | active_by_runs)

    credits_sold = int(
        db.execute(
            select(func.coalesce(func.sum(PaymentRecord.credits_added), 0)).where(
                PaymentRecord.status == "paid"
            )
        ).scalar_one()
        or 0
    )
    credits_consumed = int(
        db.execute(
            select(func.coalesce(func.sum(ApiUsageEvent.credits_cost), 0)).where(
                ApiUsageEvent.provider != _ADMIN_PROVIDER,
                ApiUsageEvent.credits_cost > 0,
            )
        ).scalar_one()
        or 0
    )
    credits_outstanding = int(
        db.execute(select(func.coalesce(func.sum(CreditWallet.balance), 0))).scalar_one() or 0
    )
    revenue_cop_total = int(
        db.execute(
            select(func.coalesce(func.sum(PaymentRecord.amount_cop), 0)).where(
                PaymentRecord.status == "paid"
            )
        ).scalar_one()
        or 0
    )
    payments_paid_count = int(
        db.execute(select(func.count(PaymentRecord.id)).where(PaymentRecord.status == "paid")).scalar_one()
        or 0
    )
    payments_pending_count = int(
        db.execute(
            select(func.count(PaymentRecord.id)).where(PaymentRecord.status == "pending")
        ).scalar_one()
        or 0
    )

    return {
        "users_total": users_total,
        "users_active_30d": users_active_30d,
        "users_registered_7d": users_registered_7d,
        "users_registered_30d": users_registered_30d,
        "credits_sold": credits_sold,
        "credits_consumed": credits_consumed,
        "credits_outstanding": credits_outstanding,
        "revenue_cop_total": revenue_cop_total,
        "payments_paid_count": payments_paid_count,
        "payments_pending_count": payments_pending_count,
        "usage_by_provider": usage_by_provider(db, exclude_providers=(_ADMIN_PROVIDER,)),
    }


@router.get("/users")
def admin_users(
    query: str = "",
    limit: int = 50,
    offset: int = 0,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    stmt = select(AppUser)
    count_stmt = select(func.count(AppUser.id))
    q = (query or "").strip()
    if q:
        like = f"%{q.lower()}%"
        cond = func.lower(AppUser.email).like(like) | func.lower(AppUser.full_name).like(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = int(db.execute(count_stmt).scalar_one() or 0)
    users = db.execute(
        stmt.order_by(AppUser.created_at.desc()).limit(max(1, min(limit, 200))).offset(max(0, offset))
    ).scalars().all()
    return {"total": total, "items": [_user_item(db, u) for u in users]}


@router.get("/users/{user_id}")
def admin_user_detail(
    user_id: int,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    payments = db.execute(
        select(PaymentRecord)
        .where(PaymentRecord.tenant_id == user.tenant_id)
        .order_by(PaymentRecord.created_at.desc())
    ).scalars().all()
    recent_runs = db.execute(
        select(AgentRun)
        .where(AgentRun.tenant_id == user.tenant_id)
        .order_by(AgentRun.created_at.desc())
        .limit(20)
    ).scalars().all()

    detail = _user_item(db, user)
    detail["usage_by_provider"] = usage_by_provider(db, tenant_id=user.tenant_id)
    detail["payments"] = [
        {
            "id": p.id,
            "reference": p.reference,
            "provider": p.provider,
            "amount_cop": p.amount_cop,
            "credits_added": p.credits_added,
            "status": p.status,
            "created_at": p.created_at,
        }
        for p in payments
    ]
    detail["recent_runs"] = [
        {
            "id": r.id,
            "status": r.status,
            "content_format": r.content_format,
            "created_at": r.created_at,
        }
        for r in recent_runs
    ]
    return detail


@router.get("/payments")
def admin_payments(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    stmt = select(PaymentRecord)
    count_stmt = select(func.count(PaymentRecord.id))
    if status_filter:
        stmt = stmt.where(PaymentRecord.status == status_filter)
        count_stmt = count_stmt.where(PaymentRecord.status == status_filter)

    total = int(db.execute(count_stmt).scalar_one() or 0)
    payments = db.execute(
        stmt.order_by(PaymentRecord.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .offset(max(0, offset))
    ).scalars().all()

    tenant_ids = {p.tenant_id for p in payments}
    email_by_tenant: dict[str, str] = {}
    if tenant_ids:
        rows = db.execute(
            select(AppUser.tenant_id, AppUser.email).where(AppUser.tenant_id.in_(tenant_ids))
        ).all()
        email_by_tenant = {t: e for t, e in rows}

    items = [
        {
            "id": p.id,
            "tenant_id": p.tenant_id,
            "email": email_by_tenant.get(p.tenant_id) or p.payer_email or "",
            "reference": p.reference,
            "provider": p.provider,
            "amount_cop": p.amount_cop,
            "credits_added": p.credits_added,
            "status": p.status,
            "created_at": p.created_at,
        }
        for p in payments
    ]
    return {"total": total, "items": items}


@router.get("/usage")
def admin_usage(
    group_by: str = "provider",
    days: int = 30,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    since = datetime.utcnow() - timedelta(days=max(1, days))

    if group_by == "user":
        rows = db.execute(
            select(
                ApiUsageEvent.tenant_id,
                func.count(ApiUsageEvent.id),
                func.coalesce(func.sum(ApiUsageEvent.units), 0),
                func.coalesce(func.sum(ApiUsageEvent.credits_cost), 0),
            )
            .where(ApiUsageEvent.created_at >= since, ApiUsageEvent.provider != _ADMIN_PROVIDER)
            .group_by(ApiUsageEvent.tenant_id)
        ).all()
        total_events = sum(r[1] for r in rows) or 1
        tenant_ids = [r[0] for r in rows]
        email_by_tenant: dict[str, str] = {}
        if tenant_ids:
            email_by_tenant = {
                t: e
                for t, e in db.execute(
                    select(AppUser.tenant_id, AppUser.email).where(AppUser.tenant_id.in_(tenant_ids))
                ).all()
            }
        items = [
            {
                "key": r[0],
                "label": email_by_tenant.get(r[0], r[0]),
                "events": int(r[1]),
                "units": int(r[2]),
                "credits": int(r[3]),
                "share_pct": round(r[1] * 100.0 / total_events, 2),
            }
            for r in rows
        ]
    else:
        by_provider = usage_by_provider(db, since=since, exclude_providers=(_ADMIN_PROVIDER,))
        items = [
            {
                "key": p["provider"],
                "label": p["provider"],
                "events": p["events"],
                "units": p["units"],
                "credits": p["credits"],
                "share_pct": p["share_pct"],
            }
            for p in by_provider
        ]

    return {"days": days, "group_by": group_by, "items": items}


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: UserUpdateRequest,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    if user.id == admin.id:
        if payload.is_admin is False:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No puedes quitarte a ti mismo el rol de administrador.",
            )
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No puedes desactivar tu propia cuenta.",
            )

    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    db.commit()
    db.refresh(user)
    return _user_item(db, user)


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordResponse)
def admin_reset_password(
    user_id: int,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetPasswordResponse:
    _ensure_enabled()
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    temporary_password = secrets.token_urlsafe(12)
    user.password_hash = _hash_password(temporary_password)
    db.commit()
    _log.info("admin.reset_password", user_id=user.id, tenant_id=user.tenant_id, admin_id=admin.id)
    return ResetPasswordResponse(
        temporary_password=temporary_password,
        note="Guarda esta contraseña temporal ahora: no se volverá a mostrar.",
    )


@router.post("/users/{user_id}/credits")
def admin_adjust_credits(
    user_id: int,
    payload: CreditAdjustRequest,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    wallet = get_or_create_wallet(db, user.tenant_id)
    new_balance = wallet.balance + payload.delta
    if new_balance < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El ajuste dejaría el saldo en negativo.",
        )
    wallet.balance = new_balance
    db.commit()
    db.refresh(wallet)

    record_usage(
        db,
        user.tenant_id,
        _ADMIN_PROVIDER,
        "credit_adjust",
        credits_cost=-payload.delta,
        model=payload.reason or "",
    )
    _log.info(
        "admin.credits_adjusted",
        user_id=user.id,
        tenant_id=user.tenant_id,
        delta=payload.delta,
        reason=payload.reason,
        admin_id=admin.id,
    )
    return {"balance": wallet.balance}
