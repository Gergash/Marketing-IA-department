"""Registro, login y JWT para staging SaaS (landing + Bold + créditos)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.settings import get_settings
from gateway.app.models.entities import AppUser, CreditWallet

_PBKDF2_ITERS = 120_000


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS)
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_hex, digest_hex = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters_s))
        return secrets.compare_digest(expected.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def register_user(db: Session, *, email: str, password: str, full_name: str = "") -> AppUser:
    email_norm = email.strip().lower()
    if not email_norm or "@" not in email_norm:
        raise ValueError("Correo inválido.")
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")

    existing = db.execute(select(AppUser).where(AppUser.email == email_norm)).scalar_one_or_none()
    if existing:
        raise ValueError("Ya existe una cuenta con ese correo. Inicia sesión.")

    tenant_id = uuid.uuid4().hex[:16]
    user = AppUser(
        email=email_norm,
        password_hash=_hash_password(password),
        tenant_id=tenant_id,
        full_name=(full_name or "").strip(),
    )
    db.add(user)
    db.add(CreditWallet(tenant_id=tenant_id, balance=0))
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> AppUser | None:
    email_norm = email.strip().lower()
    user = db.execute(select(AppUser).where(AppUser.email == email_norm)).scalar_one_or_none()
    if not user or not _verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(*, email: str, tenant_id: str) -> str:
    s = get_settings()
    secret = (s.jwt_secret or "dev-staging-change-me").strip()
    ttl = max(60, int(s.jwt_ttl_minutes or 10080))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "tenant_id": tenant_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    s = get_settings()
    secret = (s.jwt_secret or "dev-staging-change-me").strip()
    return jwt.decode(token, secret, algorithms=["HS256"])


def user_from_token(db: Session, token: str) -> AppUser | None:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    email = str(payload.get("sub") or "").strip().lower()
    if not email:
        return None
    return db.execute(select(AppUser).where(AppUser.email == email)).scalar_one_or_none()
