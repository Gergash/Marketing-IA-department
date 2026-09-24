"""Validación de ID tokens Auth0 (JWKS) y provisión de AppUser por `sub`.

Sustituye el JWT HS256 local (auth_users.create_access_token). Flujo:
1) SPA manda ID token Auth0 (RS256).
2) Verificamos firma vía JWKS del tenant.
3) Upsert AppUser.auth0_sub + CreditWallet (seed staging si aplica).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from functools import lru_cache

import jwt
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.settings import get_settings
from gateway.app.models.entities import AppUser, CreditWallet


@lru_cache(maxsize=4)
def _jwks_client(domain: str) -> PyJWKClient:
    """Cliente JWKS cacheado por dominio Auth0 (evita fetch en cada request)."""
    return PyJWKClient(f"https://{domain}/.well-known/jwks.json", cache_keys=True)


def decode_auth0_token(token: str) -> dict:
    """Valida un JWT de Auth0 (ID token o access token con aud = client_id / API).

    Reloj Windows vs Auth0: a menudo `iat` futuro ("not yet valid") o `exp` pasado.
    - leeway=600 cubre exp/nbf
    - verify_iat=False: iat no aporta seguridad si ya validamos exp+RS256+iss+aud
    Requiere paquete cryptography (PyJWT[crypto]) para RS256.
    """
    s = get_settings()
    domain = (s.auth0_domain or "").strip().removeprefix("https://").rstrip("/")
    client_id = (s.auth0_client_id or "").strip()
    if not domain or not client_id:
        raise jwt.InvalidTokenError("Auth0 no configurado (AUTH0_DOMAIN / AUTH0_CLIENT_ID).")

    audience = (s.auth0_audience or "").strip() or client_id
    issuer = f"https://{domain}/"
    signing_key = _jwks_client(domain).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        leeway=600,
        options={
            "require": ["exp", "iss", "sub"],
            "verify_iat": False,
        },
    )


def upsert_user_from_auth0(
    db: Session,
    *,
    auth0_sub: str,
    email: str,
    full_name: str = "",
) -> AppUser:
    """Crea o actualiza AppUser ligado a Auth0. Sin contraseña local.

    Usuario nuevo → wallet con STAGING_SEED_CREDITS.
    Usuario existente con saldo 0 en staging → rellena seed (E2E sin Bold).
    """
    sub = (auth0_sub or "").strip()
    if not sub:
        raise ValueError("Token Auth0 sin sub.")
    email_norm = (email or "").strip().lower()
    if not email_norm or "@" not in email_norm:
        raise ValueError("Token Auth0 sin email verificado.")

    user = db.execute(select(AppUser).where(AppUser.auth0_sub == sub)).scalar_one_or_none()
    if user is None:
        user = db.execute(select(AppUser).where(AppUser.email == email_norm)).scalar_one_or_none()

    seed = max(0, int(get_settings().staging_seed_credits or 0))

    if user is None:
        tenant_id = uuid.uuid4().hex[:16]
        user = AppUser(
            email=email_norm,
            password_hash="",
            auth0_sub=sub,
            tenant_id=tenant_id,
            full_name=(full_name or "").strip(),
            is_active=True,
        )
        db.add(user)
        db.add(CreditWallet(tenant_id=tenant_id, balance=seed))
    else:
        user.auth0_sub = sub
        user.email = email_norm
        if full_name and not (user.full_name or "").strip():
            user.full_name = full_name.strip()
        user.password_hash = user.password_hash or ""
        # Staging: ensure returning users can publish (wallet missing or empty).
        if seed > 0 and get_settings().staging_saas_enabled:
            wallet = db.execute(
                select(CreditWallet).where(CreditWallet.tenant_id == user.tenant_id)
            ).scalar_one_or_none()
            if wallet is None:
                db.add(CreditWallet(tenant_id=user.tenant_id, balance=seed))
            elif wallet.balance <= 0:
                wallet.balance = seed

    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def resolve_tenant_from_auth0_token(db: Session, token: str) -> tuple[str, AppUser]:
    """Punto de entrada para require_auth: claims → upsert → tenant_id."""
    claims = decode_auth0_token(token)
    sub = str(claims.get("sub") or "")
    email = str(claims.get("email") or claims.get("https://marketing.depa/email") or "")
    name = str(claims.get("name") or claims.get("nickname") or "")
    user = upsert_user_from_auth0(db, auth0_sub=sub, email=email, full_name=name)
    return user.tenant_id, user
