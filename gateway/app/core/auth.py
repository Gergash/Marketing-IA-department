"""Autenticación Bearer: JWT (staging SaaS) o API key legacy."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from gateway.app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)


def _looks_like_jwt(token: str) -> bool:
    parts = (token or "").split(".")
    return len(parts) == 3 and all(parts)


def _tenant_from_jwt(token: str) -> str:
    from gateway.app.services.auth_users import decode_access_token

    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sesión inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    tenant_id = str(payload.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin tenant_id.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return tenant_id


def _ensure_tenant_active(db: Session, tenant_id: str) -> None:
    """403 si el AppUser del tenant existe y fue desactivado desde el panel de administrador."""
    from sqlalchemy import select

    from gateway.app.models.entities import AppUser

    user = db.execute(select(AppUser).where(AppUser.tenant_id == tenant_id)).scalar_one_or_none()
    if user is not None and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada. Contacta al administrador.",
        )


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> str:
    """Valida Bearer y retorna tenant_id.

    Prioridad:
    1. JWT si staging SaaS activo y el token parece JWT
    2. API_KEY legacy (un solo tenant demo)
    3. Sin API_KEY → tenant demo (dev clásico)
    """
    from gateway.app.core.settings import get_settings

    s = get_settings()
    token = credentials.credentials if credentials else ""

    if token and s.staging_saas_enabled and _looks_like_jwt(token):
        tenant_id = _tenant_from_jwt(token)
        _ensure_tenant_active(db, tenant_id)
        return tenant_id

    if s.api_key:
        if not credentials or token != s.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key inválida o ausente. Header: Authorization: Bearer <API_KEY>",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return s.default_tenant_id

    if token and _looks_like_jwt(token):
        tenant_id = _tenant_from_jwt(token)
        _ensure_tenant_active(db, tenant_id)
        return tenant_id

    if not s.api_key:
        return s.default_tenant_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticación requerida.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Exige que el tenant autenticado sea administrador; devuelve el `AppUser`.

    Bootstrap: cualquier email listado en `settings.admin_emails` (coma-separada) es
    admin aunque su fila `AppUser.is_admin` sea False — sin esto, nadie podría volverse
    admin la primera vez porque el único endpoint para marcar `is_admin=True` requiere
    ya ser admin.
    """
    from sqlalchemy import select

    from gateway.app.core.settings import get_settings
    from gateway.app.models.entities import AppUser

    user = db.execute(select(AppUser).where(AppUser.tenant_id == tenant_id)).scalar_one_or_none()
    admin_emails = {
        e.strip().lower() for e in (get_settings().admin_emails or "").split(",") if e.strip()
    }
    is_admin = bool(user is not None and (user.is_admin or user.email.lower() in admin_emails))
    if not user or not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a administradores.",
        )
    return user
