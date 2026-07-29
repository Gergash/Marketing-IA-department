"""Flujo OAuth 2.0 nativo para Meta (Instagram/Facebook) y LinkedIn."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.auth import require_auth
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models import OAuthToken

router = APIRouter(prefix="/api/auth")

# CSRF state store en memoria (un solo proceso, dev)
_pending_states: dict[str, str] = {}

_INSTAGRAM_GRANULAR_SCOPES = frozenset({"instagram_basic", "instagram_content_publish"})


@router.get("/login/{provider}")
def oauth_login(
    provider: str,
    tenant_id: str = Depends(require_auth),
) -> RedirectResponse:
    """Redirige al usuario a la URL de autorización de Meta o LinkedIn."""
    s = get_settings()
    state = secrets.token_urlsafe(16)
    _pending_states[state] = tenant_id

    if provider == "meta":
        if not s.meta_client_id:
            raise HTTPException(status_code=400, detail="META_CLIENT_ID no configurado en .env")
        scopes = "pages_show_list,instagram_basic,instagram_content_publish,pages_read_engagement"
        auth_url = (
            f"https://www.facebook.com/dialog/oauth"
            f"?client_id={s.meta_client_id}"
            f"&redirect_uri={s.meta_redirect_uri}"
            f"&scope={scopes}"
            f"&response_type=code"
            f"&state={state}"
        )
    elif provider == "linkedin":
        if not s.linkedin_client_id:
            raise HTTPException(status_code=400, detail="LINKEDIN_CLIENT_ID no configurado en .env")
        # Community Management API (Share/Posts) + Sign In with LinkedIn (OpenID).
        # w_member_social: publicar como miembro. r_liteprofile está deprecado → openid/profile.
        scopes = "openid profile w_member_social"
        auth_url = (
            f"https://www.linkedin.com/oauth/v2/authorization"
            f"?response_type=code"
            f"&client_id={s.linkedin_client_id}"
            f"&redirect_uri={s.linkedin_redirect_uri}"
            f"&scope={scopes}"
            f"&state={state}"
        )
    elif provider == "google":
        if not s.google_client_id:
            raise HTTPException(status_code=400, detail="GOOGLE_CLIENT_ID no configurado en .env")
        # access_type=offline + prompt=consent: obligatorio para recibir refresh_token (Celery-safe, headless)
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={s.google_client_id}"
            f"&redirect_uri={s.google_redirect_uri}"
            f"&scope=https://www.googleapis.com/auth/drive.readonly"
            f"&response_type=code"
            f"&access_type=offline"
            f"&prompt=consent"
            f"&state={state}"
        )
    else:
        raise HTTPException(status_code=400, detail=f"Proveedor '{provider}' no soportado. Usa: meta | linkedin | google")

    return RedirectResponse(auth_url)


@router.get("/callback/{provider}")
def oauth_callback(
    provider: str,
    state: str,
    db: Session = Depends(get_db),
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Recibe el authorization code, lo intercambia por token y lo persiste en oauth_tokens."""
    if error:
        return _oauth_frontend_redirect(
            provider,
            oauth="error",
            message=error_description or error,
        )

    if not code:
        return _oauth_frontend_redirect(
            provider,
            oauth="error",
            message="No se recibió código de autorización.",
        )

    tenant_id = _pending_states.pop(state, None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="State inválido o expirado. Inicia el flujo desde /api/auth/login/{provider}.")

    s = get_settings()

    try:
        if provider == "meta":
            token_data = _exchange_meta(code, s)
            accounts = _fetch_meta_ig_accounts(token_data["access_token"], s)
        elif provider == "linkedin":
            token_data = _exchange_linkedin(code, s)
            accounts = [_fetch_linkedin_account(token_data["access_token"])]
        elif provider == "google":
            token_data = _exchange_google(code, s)
            accounts = [{"account_id": _fetch_google_account(token_data["access_token"])}]
        else:
            raise HTTPException(status_code=400, detail=f"Proveedor '{provider}' no soportado.")

        # Multi-cuenta: upsert por (tenant, provider, account_id) — conectar una cuenta
        # nueva NO desconecta las anteriores; reconectar la misma refresca su token.
        now = datetime.utcnow()
        for acc in accounts:
            _upsert_oauth_account(db, tenant_id, provider, token_data, acc, now)
        db.commit()
    except HTTPException as exc:
        return _oauth_frontend_redirect(provider, oauth="error", message=str(exc.detail))

    account_id = ",".join(a["account_id"] for a in accounts)
    return _oauth_frontend_redirect(
        provider,
        oauth="success",
        account_id=account_id,
        fallback_payload={
            "status": "connected",
            "provider": provider,
            "account_id": account_id,
            "message": f"Cuenta {provider} vinculada correctamente. Ya puedes cerrar esta ventana.",
        },
    )


def _upsert_oauth_account(
    db: Session,
    tenant_id: str,
    provider: str,
    token_data: dict,
    account: dict,
    now: datetime,
) -> None:
    """Inserta o refresca una cuenta social. `account` puede traer un token propio (Page token de Meta)."""
    access_token = account.get("access_token") or token_data["access_token"]
    existing = db.execute(
        select(OAuthToken).where(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.provider == provider,
            OAuthToken.account_id == account["account_id"],
        )
    ).scalar_one_or_none()

    if existing:
        existing.access_token = access_token
        existing.refresh_token = token_data.get("refresh_token")
        existing.expires_at = token_data.get("expires_at")
        existing.account_name = account.get("account_name") or existing.account_name
        existing.profile_picture_url = account.get("profile_picture_url") or existing.profile_picture_url
        existing.page_id = account.get("page_id") or existing.page_id
        existing.is_active = True
        existing.updated_at = now
    else:
        db.add(OAuthToken(
            tenant_id=tenant_id,
            provider=provider,
            access_token=access_token,
            refresh_token=token_data.get("refresh_token"),
            expires_at=token_data.get("expires_at"),
            account_id=account["account_id"],
            account_name=account.get("account_name"),
            profile_picture_url=account.get("profile_picture_url"),
            page_id=account.get("page_id"),
            is_active=True,
            created_at=now,
            updated_at=now,
        ))


@router.get("/status")
def oauth_status(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Devuelve qué proveedores tiene conectados el tenant (sin exponer tokens)."""
    rows = db.execute(
        select(OAuthToken.provider, OAuthToken.account_id, OAuthToken.updated_at).where(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.is_active.is_(True),
        )
    ).all()
    return {
        "connected": [
            {"provider": r.provider, "account_id": r.account_id, "updated_at": r.updated_at.isoformat()}
            for r in rows
        ]
    }


@router.get("/accounts")
def list_social_accounts(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Lista las cuentas sociales conectadas del tenant para el selector de cuenta destino."""
    rows = db.execute(
        select(OAuthToken)
        .where(OAuthToken.tenant_id == tenant_id, OAuthToken.is_active.is_(True))
        .order_by(OAuthToken.provider, OAuthToken.id)
    ).scalars().all()
    return {
        "accounts": [
            {
                "id": r.id,
                "provider": r.provider,
                "account_id": r.account_id,
                "account_name": r.account_name,
                "profile_picture_url": r.profile_picture_url,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.delete("/accounts/{account_row_id}")
def disconnect_social_account(
    account_row_id: int,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Desconexión lógica: marca la cuenta como inactiva sin borrar el historial."""
    row = db.get(OAuthToken, account_row_id)
    if not row or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "disconnected", "id": account_row_id, "provider": row.provider}


# ---------------------------------------------------------------------------
# Helpers de intercambio de tokens
# ---------------------------------------------------------------------------

def _graph_base(s) -> str:
    ver = (s.graph_api_version or "v21.0").strip().lstrip("/")
    return f"https://graph.facebook.com/{ver}"


def _meta_app_access_token(s) -> str:
    app_id = (s.meta_client_id or s.meta_app_id).strip()
    app_secret = (s.meta_client_secret or s.meta_app_secret).strip()
    return f"{app_id}|{app_secret}"


def _oauth_frontend_redirect(
    provider: str,
    *,
    oauth: str,
    account_id: str = "",
    message: str = "",
    fallback_payload: dict | None = None,
):
    """Redirige al frontend tras OAuth si OAUTH_SUCCESS_REDIRECT_URL está configurado."""
    s = get_settings()
    base = (s.oauth_success_redirect_url or "").strip()
    if base:
        params: dict[str, str] = {"oauth": oauth, "provider": provider}
        if account_id:
            params["account_id"] = account_id
        if message:
            params["message"] = message
        sep = "&" if "?" in base else "?"
        return RedirectResponse(url=f"{base}{sep}{urlencode(params)}", status_code=302)
    if fallback_payload is not None:
        return fallback_payload
    raise HTTPException(status_code=400, detail=message or "OAuth falló")


def _exchange_meta(code: str, s) -> dict:
    """Intercambia authorization code por access token de Meta."""
    with httpx.Client(timeout=15) as client:
        r = client.get(
            f"{_graph_base(s)}/oauth/access_token",
            params={
                "client_id": s.meta_client_id,
                "client_secret": s.meta_client_secret,
                "redirect_uri": s.meta_redirect_uri,
                "code": code,
            },
        )
        r.raise_for_status()
        data = r.json()
    return {"access_token": data["access_token"], "refresh_token": None, "expires_at": None}


def _ig_id_for_page(client: httpx.Client, base: str, page_id: str, token: str) -> str:
    """Resuelve el Instagram Business Account ID vinculado a una Fan Page."""
    r_ig = client.get(
        f"{base}/{page_id}",
        params={"fields": "instagram_business_account", "access_token": token},
    )
    r_ig.raise_for_status()
    ig = r_ig.json().get("instagram_business_account") or {}
    ig_id = str(ig.get("id") or "")
    if not ig_id:
        raise HTTPException(
            status_code=400,
            detail="La página de Facebook no tiene cuenta de Instagram Business vinculada.",
        )
    return ig_id


def _ig_id_from_granular_scopes(client: httpx.Client, base: str, token: str, s) -> str | None:
    """Lee target_ids de Instagram en debug_token (permisos granulares de Meta)."""
    r = client.get(
        f"{base}/debug_token",
        params={"input_token": token, "access_token": _meta_app_access_token(s)},
    )
    if not r.is_success:
        return None
    data: dict[str, Any] = r.json().get("data") or {}
    if not data.get("is_valid"):
        return None
    for entry in data.get("granular_scopes") or []:
        if entry.get("scope") not in _INSTAGRAM_GRANULAR_SCOPES:
            continue
        for target_id in entry.get("target_ids") or []:
            if target_id:
                return str(target_id)
    return None


def _ig_id_from_configured_page(client: httpx.Client, base: str, token: str, s) -> str | None:
    """Usa META_FACEBOOK_PAGE_ID del .env cuando /me/accounts viene vacío."""
    page_id = (s.meta_facebook_page_id or "").strip()
    if not page_id:
        return None
    try:
        return _ig_id_for_page(client, base, page_id, token)
    except HTTPException:
        return None


def _ig_id_from_env_fallback(client: httpx.Client, base: str, token: str, s) -> str | None:
    """Valida INSTAGRAM_BUSINESS_ACCOUNT_ID del .env contra el token OAuth."""
    ig_id = (s.instagram_business_account_id or "").strip()
    if not ig_id:
        return None
    r_check = client.get(
        f"{base}/{ig_id}",
        params={"fields": "id", "access_token": token},
    )
    if r_check.is_success and r_check.json().get("id"):
        return ig_id
    return None


def _ig_account_for_page(client: httpx.Client, base: str, page: dict, user_token: str) -> dict | None:
    """Arma el dict de cuenta IG para una Fan Page; None si la página no tiene IG vinculado."""
    page_id = str(page["id"])
    page_token = page.get("access_token") or user_token
    r_ig = client.get(
        f"{base}/{page_id}",
        params={
            "fields": "name,instagram_business_account{id,username,profile_picture_url}",
            "access_token": page_token,
        },
    )
    if not r_ig.is_success:
        return None
    data = r_ig.json()
    ig = data.get("instagram_business_account") or {}
    ig_id = str(ig.get("id") or "")
    if not ig_id:
        return None
    return {
        "account_id": ig_id,
        "account_name": ig.get("username") or data.get("name") or page.get("name"),
        "profile_picture_url": ig.get("profile_picture_url"),
        "page_id": page_id,
        # Page token: es el que Graph API espera para publicar en la IG de esa página
        "access_token": page_token,
    }


def _fetch_meta_ig_accounts(token: str, s) -> list[dict]:
    """Obtiene TODAS las cuentas IG Business accesibles (una por Fan Page con IG vinculado).

    Fallbacks del flujo anterior (granular scopes, página del .env) devuelven una sola cuenta.
    """
    base = _graph_base(s)
    with httpx.Client(timeout=15) as client:
        r_pages = client.get(
            f"{base}/me/accounts",
            params={"fields": "id,name,access_token", "access_token": token},
        )
        r_pages.raise_for_status()
        pages = r_pages.json().get("data", [])

        accounts = []
        for page in pages:
            acc = _ig_account_for_page(client, base, page, token)
            if acc:
                accounts.append(acc)
        if accounts:
            return accounts

        ig_id = (
            _ig_id_from_granular_scopes(client, base, token, s)
            or _ig_id_from_configured_page(client, base, token, s)
            or _ig_id_from_env_fallback(client, base, token, s)
        )
        if ig_id:
            return [{"account_id": ig_id}]

    raise HTTPException(
        status_code=400,
        detail=(
            "No hay páginas de Facebook con Instagram Business vinculado en esta cuenta. "
            "Selecciona las páginas en el popup de OAuth o configura "
            "META_FACEBOOK_PAGE_ID / INSTAGRAM_BUSINESS_ACCOUNT_ID en .env."
        ),
    )


def _exchange_linkedin(code: str, s) -> dict:
    """Intercambia authorization code por access token de LinkedIn."""
    with httpx.Client(timeout=15) as client:
        r = client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": s.linkedin_redirect_uri,
                "client_id": s.linkedin_client_id,
                "client_secret": s.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        data = r.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": None,
    }


def _exchange_google(code: str, s) -> dict:
    """Intercambia authorization code por access/refresh token de Google (Drive)."""
    with httpx.Client(timeout=15) as client:
        r = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": s.google_redirect_uri,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        data = r.json()

    expires_at = None
    if data.get("expires_in"):
        expires_at = datetime.utcnow() + timedelta(seconds=int(data["expires_in"]))

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": expires_at,
    }


def _fetch_google_account(token: str) -> str:
    """Obtiene el email de la cuenta de Google conectada (userinfo)."""
    with httpx.Client(timeout=10) as client:
        r = client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json().get("email", "")


def _fetch_linkedin_account(token: str) -> dict:
    """Obtiene URN + nombre + foto vía OpenID userinfo (fallback /v2/me solo con URN)."""
    with httpx.Client(timeout=10) as client:
        r = client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.is_success:
            data = r.json()
            sub = data.get("sub")
            if sub:
                return {
                    "account_id": f"urn:li:person:{sub}",
                    "account_name": data.get("name"),
                    "profile_picture_url": data.get("picture"),
                }
        r_me = client.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        r_me.raise_for_status()
        return {"account_id": f"urn:li:person:{r_me.json()['id']}"}
