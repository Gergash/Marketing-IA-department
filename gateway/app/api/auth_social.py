"""Flujo OAuth nativo: Meta/LinkedIn/Google (OAuth 2.0) y X/Twitter (OAuth 1.0a)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from math import ceil
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from oauthlib.oauth1 import Client as OAuth1Client
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.auth import require_auth
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models import OAuthToken

router = APIRouter(prefix="/api/auth")

# CSRF state store en memoria (un solo proceso, dev) — OAuth 2.0
_pending_states: dict[str, str] = {}
# OAuth 1.0a request tokens de X: oauth_token → {tenant_id, oauth_token_secret}
_pending_x_request_tokens: dict[str, dict[str, str]] = {}

_INSTAGRAM_GRANULAR_SCOPES = frozenset({"instagram_basic", "instagram_content_publish"})


@router.get("/login/{provider}")
def oauth_login(
    provider: str,
    tenant_id: str = Depends(require_auth),
) -> RedirectResponse:
    """Redirige al usuario a la URL de autorización de Meta, LinkedIn, Google o X."""
    s = get_settings()
    if provider == "twitter":
        provider = "x"

    if provider == "x":
        if not (s.x_api_key or "").strip() or not (s.x_api_secret or "").strip():
            raise HTTPException(status_code=400, detail="X_API_KEY / X_API_SECRET no configurados en .env")
        request_tok = _x_request_token(s)
        _pending_x_request_tokens[request_tok["oauth_token"]] = {
            "tenant_id": tenant_id,
            "oauth_token_secret": request_tok["oauth_token_secret"],
        }
        auth_url = (
            "https://api.twitter.com/oauth/authorize?"
            + urlencode({"oauth_token": request_tok["oauth_token"]})
        )
        return RedirectResponse(auth_url)

    state = secrets.token_urlsafe(16)
    _pending_states[state] = tenant_id

    if provider == "meta":
        if not s.meta_client_id:
            raise HTTPException(status_code=400, detail="META_CLIENT_ID no configurado en .env")
        scopes = "pages_show_list,instagram_basic,instagram_content_publish,pages_read_engagement,pages_manage_posts"
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
        # quote_via=quote (no quote_plus): LinkedIn separa scopes por %20 y no
        # interpreta '+' como espacio → "Bummer, something went wrong".
        # El redirect_uri además debe coincidir exacto con "Authorized redirect URLs".
        auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(
            {
                "response_type": "code",
                "client_id": s.linkedin_client_id,
                "redirect_uri": s.linkedin_redirect_uri,
                "scope": s.linkedin_scopes,
                "state": state,
            },
            quote_via=quote,
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
        raise HTTPException(
            status_code=400,
            detail=f"Proveedor '{provider}' no soportado. Usa: meta | linkedin | google | x",
        )

    return RedirectResponse(auth_url)


@router.get("/callback/{provider}")
def oauth_callback(
    provider: str,
    db: Session = Depends(get_db),
    state: str | None = None,
    code: str | None = None,
    oauth_token: str | None = None,
    oauth_verifier: str | None = None,
    denied: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Recibe el authorization code (OAuth2) o oauth_verifier (X OAuth1) y persiste tokens."""
    if provider == "twitter":
        provider = "x"

    if provider == "x":
        return _oauth_callback_x(
            db,
            oauth_token=oauth_token,
            oauth_verifier=oauth_verifier,
            denied=denied,
            error=error,
            error_description=error_description,
        )

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

    tenant_id = _pending_states.pop(state or "", None)
    if not tenant_id:
        # Siempre volver al frontend: un 400 JSON en la pestaña de Meta/ngrok
        # deja al usuario sin retorno al dashboard.
        return _oauth_frontend_redirect(
            provider,
            oauth="error",
            message="State inválido o expirado. Vuelve a pulsar Conectar desde Integraciones.",
        )

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
    except Exception as exc:
        # Errores de DB/red no deben dejar al usuario en una página JSON de ngrok.
        db.rollback()
        return _oauth_frontend_redirect(
            provider,
            oauth="error",
            message=f"No se pudo guardar la cuenta {provider}: {exc}",
        )

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


def _oauth_callback_x(
    db: Session,
    *,
    oauth_token: str | None,
    oauth_verifier: str | None,
    denied: str | None,
    error: str | None,
    error_description: str | None,
):
    """Completa el 3-legged OAuth 1.0a de X y guarda access token + secret."""
    if denied is not None or error:
        return _oauth_frontend_redirect(
            "x",
            oauth="error",
            message=error_description or error or "Autorización denegada en X.",
        )
    if not oauth_token or not oauth_verifier:
        return _oauth_frontend_redirect(
            "x",
            oauth="error",
            message="X no devolvió oauth_token/oauth_verifier. Vuelve a Conectar X.",
        )

    pending = _pending_x_request_tokens.pop(oauth_token, None)
    if not pending:
        return _oauth_frontend_redirect(
            "x",
            oauth="error",
            message="Request token de X inválido o expirado. Vuelve a pulsar Conectar X.",
        )

    s = get_settings()
    try:
        token_data, account = _x_access_token(
            s,
            oauth_token=oauth_token,
            oauth_token_secret=pending["oauth_token_secret"],
            oauth_verifier=oauth_verifier,
        )
        _upsert_oauth_account(db, pending["tenant_id"], "x", token_data, account, datetime.utcnow())
        db.commit()
    except HTTPException as exc:
        return _oauth_frontend_redirect("x", oauth="error", message=str(exc.detail))
    except Exception as exc:
        db.rollback()
        return _oauth_frontend_redirect(
            "x",
            oauth="error",
            message=f"No se pudo guardar la cuenta X: {exc}",
        )

    return _oauth_frontend_redirect(
        "x",
        oauth="success",
        account_id=account["account_id"],
        fallback_payload={
            "status": "connected",
            "provider": "x",
            "account_id": account["account_id"],
            "message": "Cuenta X vinculada correctamente. Ya puedes cerrar esta ventana.",
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


EXPIRY_WARNING_DAYS = 7


def token_expiry_info(expires_at: datetime | None, now: datetime | None = None) -> dict:
    """Traduce `expires_at` a banderas que la UI puede mostrar sin recalcular fechas."""
    if expires_at is None:
        return {"expires_at": None, "expires_in_days": None, "is_expired": False, "expires_soon": False}
    now = now or datetime.utcnow()
    remaining_days = (expires_at - now).total_seconds() / 86400
    is_expired = remaining_days <= 0
    return {
        "expires_at": expires_at.isoformat(),
        # Techo: quedan horas → "1 d", no "0 d" (que se leería como caducado).
        "expires_in_days": ceil(remaining_days) if not is_expired else 0,
        "is_expired": is_expired,
        "expires_soon": not is_expired and remaining_days <= EXPIRY_WARNING_DAYS,
    }


@router.get("/status")
def oauth_status(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Devuelve qué proveedores tiene conectados el tenant (sin exponer tokens)."""
    rows = db.execute(
        select(
            OAuthToken.provider,
            OAuthToken.account_id,
            OAuthToken.updated_at,
            OAuthToken.expires_at,
        ).where(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.is_active.is_(True),
        )
    ).all()
    return {
        "connected": [
            {
                "provider": r.provider,
                "account_id": r.account_id,
                "updated_at": r.updated_at.isoformat(),
                **token_expiry_info(r.expires_at),
            }
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
                **token_expiry_info(r.expires_at),
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

    # LinkedIn devuelve expires_in (~60 días). Sin persistirlo, el token caduca en
    # silencio y el fallo solo aparece al aprobar un run.
    expires_at = None
    if data.get("expires_in"):
        expires_at = datetime.utcnow() + timedelta(seconds=int(data["expires_in"]))

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": expires_at,
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
    """Obtiene la identidad del miembro: OpenID userinfo, o /v2/me si la app usa r_basicprofile."""
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=10) as client:
        # Camino moderno: producto "Sign In with LinkedIn using OpenID Connect".
        r = client.get("https://api.linkedin.com/v2/userinfo", headers=headers)
        if r.is_success and r.json().get("sub"):
            data = r.json()
            return {
                "account_id": f"urn:li:person:{data['sub']}",
                "account_name": data.get("name"),
                "profile_picture_url": data.get("picture"),
            }

        # Camino clásico: apps con r_basicprofile y sin el producto OpenID.
        r_me = client.get("https://api.linkedin.com/v2/me", headers=headers)
        if not r_me.is_success:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se pudo leer el perfil de LinkedIn: el token no tiene ni `profile` (OpenID) "
                    "ni `r_basicprofile`. Habilita 'Sign In with LinkedIn using OpenID Connect' en "
                    "Products, o ajusta LINKEDIN_SCOPES a los scopes que muestre la pestaña Auth."
                ),
            )
        me = r_me.json()
        name = " ".join(
            part for part in (me.get("localizedFirstName"), me.get("localizedLastName")) if part
        )
        return {"account_id": f"urn:li:person:{me['id']}", "account_name": name or None}


# ---------------------------------------------------------------------------
# X (Twitter) — OAuth 1.0a 3-legged
# Docs: https://developer.x.com/en/docs/authentication/oauth-1-0a
# ---------------------------------------------------------------------------

def _x_oauth1_client(
    s,
    *,
    resource_owner_key: str | None = None,
    resource_owner_secret: str | None = None,
    verifier: str | None = None,
    callback_uri: str | None = None,
) -> OAuth1Client:
    """Cliente OAuth1 firmado con Consumer Key/Secret (y tokens de usuario si aplica)."""
    return OAuth1Client(
        client_key=(s.x_api_key or "").strip(),
        client_secret=(s.x_api_secret or "").strip(),
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
        callback_uri=callback_uri,
        signature_type="AUTH_HEADER",
    )


def _x_signed_post(url: str, client: OAuth1Client) -> str:
    """POST form-urlencoded firmado; devuelve el body de texto (querystring)."""
    uri, headers, body = client.sign(url, http_method="POST")
    with httpx.Client(timeout=20) as http:
        r = http.post(uri, content=body or b"", headers=dict(headers))
    if not r.is_success:
        raise HTTPException(
            status_code=400,
            detail=f"X OAuth HTTP {r.status_code}: {r.text[:300]}",
        )
    return r.text


def _x_request_token(s) -> dict[str, str]:
    """Paso 1: obtiene request token + secret con callback_uri = X_REDIRECT_URI."""
    client = _x_oauth1_client(s, callback_uri=(s.x_redirect_uri or "").strip())
    raw = _x_signed_post("https://api.twitter.com/oauth/request_token", client)
    data = dict(parse_qsl(raw, keep_blank_values=True))
    token = data.get("oauth_token") or ""
    secret = data.get("oauth_token_secret") or ""
    if not token or not secret:
        raise HTTPException(status_code=400, detail=f"X request_token incompleto: {raw[:200]}")
    if data.get("oauth_callback_confirmed") not in (None, "true"):
        raise HTTPException(status_code=400, detail="X no confirmó oauth_callback")
    return {"oauth_token": token, "oauth_token_secret": secret}


def _x_access_token(
    s,
    *,
    oauth_token: str,
    oauth_token_secret: str,
    oauth_verifier: str,
) -> tuple[dict, dict]:
    """Paso 3: intercambia request token + verifier por access token de usuario."""
    client = _x_oauth1_client(
        s,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_token_secret,
        verifier=oauth_verifier,
    )
    raw = _x_signed_post("https://api.twitter.com/oauth/access_token", client)
    data = dict(parse_qsl(raw, keep_blank_values=True))
    access = data.get("oauth_token") or ""
    secret = data.get("oauth_token_secret") or ""
    user_id = data.get("user_id") or ""
    screen_name = data.get("screen_name") or ""
    if not access or not secret or not user_id:
        raise HTTPException(status_code=400, detail=f"X access_token incompleto: {raw[:200]}")
    # access_token = user oauth_token; refresh_token reutilizado para oauth_token_secret
    token_data = {
        "access_token": access,
        "refresh_token": secret,
        "expires_at": None,
    }
    account = {
        "account_id": user_id,
        "account_name": f"@{screen_name}" if screen_name else user_id,
    }
    return token_data, account

