from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Valida Bearer API key. Retorna tenant_id.

    Si API_KEY está vacía en .env, el modo auth está desactivado (dev local).
    En cualquier otro caso, la key debe coincidir exactamente.
    """
    from gateway.app.core.settings import get_settings
    s = get_settings()

    if not s.api_key:
        return s.default_tenant_id

    if not credentials or credentials.credentials != s.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente. Header requerido: Authorization: Bearer <API_KEY>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return s.default_tenant_id
