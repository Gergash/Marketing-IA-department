"""Registro e inicio de sesión para staging SaaS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.auth import require_auth
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models.entities import AppUser
from gateway.app.services.auth_users import authenticate_user, create_access_token, register_user
from gateway.app.services.credits_service import get_or_create_wallet

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    tenant_id: str
    full_name: str = ""
    credits_balance: int = 0


class MeResponse(BaseModel):
    email: str
    tenant_id: str
    full_name: str = ""
    credits_balance: int
    staging_enabled: bool


def _ensure_staging() -> None:
    if not get_settings().staging_saas_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro/login SaaS no activo en este entorno.",
        )


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    _ensure_staging()
    try:
        user = register_user(
            db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    wallet = get_or_create_wallet(db, user.tenant_id)
    token = create_access_token(email=user.email, tenant_id=user.tenant_id)
    return AuthResponse(
        access_token=token,
        email=user.email,
        tenant_id=user.tenant_id,
        full_name=user.full_name or "",
        credits_balance=wallet.balance,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    _ensure_staging()
    user = authenticate_user(db, email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        )
    wallet = get_or_create_wallet(db, user.tenant_id)
    token = create_access_token(email=user.email, tenant_id=user.tenant_id)
    return AuthResponse(
        access_token=token,
        email=user.email,
        tenant_id=user.tenant_id,
        full_name=user.full_name or "",
        credits_balance=wallet.balance,
    )


@router.get("/me", response_model=MeResponse)
def me(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> MeResponse:
    s = get_settings()
    wallet = get_or_create_wallet(db, tenant_id)
    user = db.execute(select(AppUser).where(AppUser.tenant_id == tenant_id)).scalar_one_or_none()
    return MeResponse(
        email=user.email if user else "",
        tenant_id=tenant_id,
        full_name=(user.full_name if user else "") or "",
        credits_balance=wallet.balance,
        staging_enabled=s.staging_saas_enabled,
    )
