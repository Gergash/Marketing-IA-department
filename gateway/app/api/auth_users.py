"""Perfil SaaS vía Auth0 (sin registro/login local).

/register y /login responden 410: la identidad es Auth0 Universal Login.
/me sigue siendo el contrato del studio (email, créditos, is_admin, auth0_sub).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.auth import require_auth
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models.entities import AppUser
from gateway.app.services.credits_service import get_or_create_wallet

router = APIRouter(prefix="/api/auth", tags=["auth"])


class MeResponse(BaseModel):
    email: str
    tenant_id: str
    full_name: str = ""
    credits_balance: int
    staging_enabled: bool
    is_admin: bool = False
    is_active: bool = True
    auth0_sub: str | None = None


def _ensure_staging() -> None:
    if not get_settings().staging_saas_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS no activo en este entorno.",
        )


def _local_auth_removed() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="El registro/login local fue eliminado. Usa Auth0 Universal Login.",
    )


@router.post("/register", include_in_schema=False)
def register_removed() -> None:
    _local_auth_removed()


@router.post("/login", include_in_schema=False)
def login_removed() -> None:
    _local_auth_removed()


@router.get("/me", response_model=MeResponse)
def me(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> MeResponse:
    from gateway.app.core.auth import require_admin

    s = get_settings()
    wallet = get_or_create_wallet(db, tenant_id)
    user = db.execute(select(AppUser).where(AppUser.tenant_id == tenant_id)).scalar_one_or_none()
    is_admin = False
    if user is not None:
        try:
            require_admin(tenant_id=tenant_id, db=db)
            is_admin = True
        except HTTPException:
            is_admin = False
    return MeResponse(
        email=user.email if user else "",
        tenant_id=tenant_id,
        full_name=(user.full_name if user else "") or "",
        credits_balance=wallet.balance,
        staging_enabled=s.staging_saas_enabled,
        is_admin=is_admin,
        is_active=bool(user.is_active) if user else True,
        auth0_sub=user.auth0_sub if user else None,
    )
