"""Autenticación Bearer: JWT (staging SaaS) o API key legacy."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
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
        return _tenant_from_jwt(token)

    if s.api_key:
        if not credentials or token != s.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key inválida o ausente. Header: Authorization: Bearer <API_KEY>",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return s.default_tenant_id

    if token and _looks_like_jwt(token):
        return _tenant_from_jwt(token)

    if not s.api_key:
        return s.default_tenant_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticación requerida.",
        headers={"WWW-Authenticate": "Bearer"},
    )
