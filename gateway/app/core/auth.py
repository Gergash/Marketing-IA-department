"""Autenticación Bearer: Auth0 (SaaS) o API key legacy.

Cambio: con STAGING_SAAS_ENABLED + AUTH0_* ya no se acepta el JWT HS256 local;
solo ID tokens Auth0 (RS256) vía auth0_jwt.resolve_tenant_from_auth0_token.
Sin Bearer en modo SaaS → 401 "Autenticación Auth0 requerida."
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from gateway.app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)


def _looks_like_jwt(token: str) -> bool:
    parts = (token or "").split(".")
    return len(parts) == 3 and all(parts)


def _auth0_configured() -> bool:
    from gateway.app.core.settings import get_settings

    s = get_settings()
    return bool((s.auth0_domain or "").strip() and (s.auth0_client_id or "").strip())


def _tenant_from_auth0(db: Session, token: str) -> str:
    from gateway.app.services.auth0_jwt import resolve_tenant_from_auth0_token

    try:
        tenant_id, _user = resolve_tenant_from_auth0_token(db, token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token Auth0 inválido o expirado: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
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
    1. Auth0 JWT si staging SaaS + AUTH0_* configurados
    2. API_KEY legacy (un solo tenant demo)
    3. Sin API_KEY y sin SaaS → tenant demo (dev clásico)
    """
    from gateway.app.core.settings import get_settings

    s = get_settings()
    token = credentials.credentials if credentials else ""

    if token and s.staging_saas_enabled and _auth0_configured() and _looks_like_jwt(token):
        tenant_id = _tenant_from_auth0(db, token)
        _ensure_tenant_active(db, tenant_id)
        return tenant_id

    if s.staging_saas_enabled and _auth0_configured():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación Auth0 requerida.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if s.api_key:
        if not credentials or token != s.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key inválida o ausente. Header: Authorization: Bearer <API_KEY>",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return s.default_tenant_id

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
    admin aunque su fila `AppUser.is_admin` sea False.
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
