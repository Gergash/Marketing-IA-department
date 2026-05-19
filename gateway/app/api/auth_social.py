"""Flujo OAuth 2.0 nativo para Meta (Instagram/Facebook) y LinkedIn."""

from __future__ import annotations

import secrets
from datetime import datetime

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
        scopes = "w_member_social r_liteprofile"
        auth_url = (
            f"https://www.linkedin.com/oauth/v2/authorization"
            f"?response_type=code"
            f"&client_id={s.linkedin_client_id}"
            f"&redirect_uri={s.linkedin_redirect_uri}"
            f"&scope={scopes}"
            f"&state={state}"
        )
    else:
        raise HTTPException(status_code=400, detail=f"Proveedor '{provider}' no soportado. Usa: meta | linkedin")

    return RedirectResponse(auth_url)


@router.get("/callback/{provider}")
def oauth_callback(
    provider: str,
    code: str,
    state: str,
    db: Session = Depends(get_db),
) -> dict:
    """Recibe el authorization code, lo intercambia por token y lo persiste en oauth_tokens."""
    tenant_id = _pending_states.pop(state, None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="State inválido o expirado. Inicia el flujo desde /api/auth/login/{provider}.")

    s = get_settings()

    if provider == "meta":
        token_data = _exchange_meta(code, s)
        account_id = _fetch_meta_ig_account(token_data["access_token"], s)
    elif provider == "linkedin":
        token_data = _exchange_linkedin(code, s)
        account_id = _fetch_linkedin_urn(token_data["access_token"])
    else:
        raise HTTPException(status_code=400, detail=f"Proveedor '{provider}' no soportado.")

    # Upsert: actualiza si ya existe, inserta si no
    existing = db.execute(
        select(OAuthToken).where(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.provider == provider,
        )
    ).scalar_one_or_none()

    now = datetime.utcnow()
    if existing:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data.get("refresh_token")
        existing.expires_at = token_data.get("expires_at")
        existing.account_id = account_id
        existing.updated_at = now
    else:
        db.add(OAuthToken(
            tenant_id=tenant_id,
            provider=provider,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_at=token_data.get("expires_at"),
            account_id=account_id,
            created_at=now,
            updated_at=now,
        ))
    db.commit()

    return {
        "status": "connected",
        "provider": provider,
        "account_id": account_id,
        "message": f"Cuenta {provider} vinculada correctamente. Ya puedes cerrar esta ventana.",
    }


@router.get("/status")
def oauth_status(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Devuelve qué proveedores tiene conectados el tenant (sin exponer tokens)."""
    rows = db.execute(
        select(OAuthToken.provider, OAuthToken.account_id, OAuthToken.updated_at).where(
            OAuthToken.tenant_id == tenant_id
        )
    ).all()
    return {
        "connected": [
            {"provider": r.provider, "account_id": r.account_id, "updated_at": r.updated_at.isoformat()}
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# Helpers de intercambio de tokens
# ---------------------------------------------------------------------------

def _exchange_meta(code: str, s) -> dict:
    """Intercambia authorization code por access token de Meta."""
    with httpx.Client(timeout=15) as client:
        r = client.get(
            f"https://graph.facebook.com/{s.graph_api_version}/oauth/access_token",
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


def _fetch_meta_ig_account(token: str, s) -> str:
    """Obtiene el Instagram Business Account ID de la primera página del usuario."""
    with httpx.Client(timeout=15) as client:
        r_pages = client.get(
            f"https://graph.facebook.com/{s.graph_api_version}/me/accounts",
            params={"access_token": token},
        )
        r_pages.raise_for_status()
        pages = r_pages.json().get("data", [])
        if not pages:
            raise HTTPException(status_code=400, detail="No hay páginas de Facebook asociadas a esta cuenta.")

        page = pages[0]
        page_id = page["id"]
        page_token = page.get("access_token", token)

        r_ig = client.get(
            f"https://graph.facebook.com/{s.graph_api_version}/{page_id}",
            params={"fields": "instagram_business_account", "access_token": page_token},
        )
        r_ig.raise_for_status()
        ig = r_ig.json().get("instagram_business_account", {})
        ig_id = ig.get("id", "")
        if not ig_id:
            raise HTTPException(status_code=400, detail="La página de Facebook no tiene cuenta de Instagram Business vinculada.")
    return ig_id


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


def _fetch_linkedin_urn(token: str) -> str:
    """Obtiene el URN `urn:li:person:{id}` del miembro autenticado."""
    with httpx.Client(timeout=10) as client:
        r = client.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return f"urn:li:person:{r.json()['id']}"
