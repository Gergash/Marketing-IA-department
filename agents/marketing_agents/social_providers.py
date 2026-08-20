"""Integraciones de publicación en redes (mock, LinkedIn, Meta/Instagram)."""

from __future__ import annotations

import hashlib
import structlog
import time
from datetime import datetime, timezone

logger = structlog.get_logger(__name__)


def publish_post(
    platform: str,
    copy_text: str,
    image_url: str,
    idempotency_key: str | None = None,
    *,
    content_format: str = "feed",
    linkedin_token: str | None = None,
    linkedin_urn: str | None = None,
    x_access_token: str | None = None,
    x_access_token_secret: str | None = None,
) -> dict:
    """Enruta la publicación según plataforma y tokens disponibles (LinkedIn, X, Meta/IG o mock)."""
    from gateway.app.core.settings import get_settings
    s = get_settings()
    cf = (content_format or "feed").lower()
    if cf not in ("feed", "story"):
        cf = "feed"

    if platform.lower() in ("linkedin",) and linkedin_token:
        return _linkedin(copy_text, image_url, linkedin_token, linkedin_urn or "", content_format=cf)
    if platform.lower() in ("x", "twitter") and x_access_token and x_access_token_secret:
        return _x_twitter(
            copy_text,
            image_url,
            x_access_token,
            x_access_token_secret,
            content_format=cf,
        )
    if (
        s.social_provider == "meta"
        and s.meta_page_access_token
        and s.instagram_business_account_id
        and platform.lower() in ("instagram", "ig")
    ):
        return _meta_instagram(copy_text, image_url, s, content_format=cf)
    return _mock(platform, copy_text, image_url, idempotency_key, content_format=cf)


# ---------------------------------------------------------------------------
# Meta — Instagram Graph API (cuenta profesional vinculada a Meta Business)
# Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing
# La imagen debe ser URL HTTPS pública accesible por los servidores de Meta.
# ---------------------------------------------------------------------------


def _meta_instagram(copy_text: str, image_url: str, s, *, content_format: str) -> dict:
    """Crea contenedor de media y publica en Instagram vía Graph API (post con caption o historia STORIES)."""
    import httpx

    # Meta exige URL HTTPS pública; sustituye localhost por PUBLIC_IMAGE_BASE_URL (ej. ngrok en dev)
    public_base = s.public_image_base_url.rstrip("/")
    if image_url.startswith("http://localhost:8000"):
        image_url = image_url.replace("http://localhost:8000", public_base, 1)

    ig_id = s.instagram_business_account_id.strip()
    token = s.meta_page_access_token.strip()
    ver = s.graph_api_version.strip().lstrip("/") or "v21.0"
    base = f"https://graph.facebook.com/{ver}"

    params = {"access_token": token}
    is_story = content_format == "story"
    media_params: dict = {**params, "image_url": image_url}
    if is_story:
        # Historia de foto: Graph API Content Publishing
        media_params["media_type"] = "STORIES"
    else:
        media_params["caption"] = copy_text[:2200]

    with httpx.Client(timeout=60) as client:
        r_media = client.post(
            f"{base}/{ig_id}/media",
            params=media_params,
        )
        if not r_media.is_success:
            logger.warning("meta.instagram.media_container_failed", body=r_media.text)
        r_media.raise_for_status()
        creation_id = r_media.json().get("id")
        if not creation_id:
            raise ValueError("Meta IG: respuesta sin id de contenedor de media")

        _wait_meta_container_ready(client, base, creation_id, params)

        r_pub = client.post(
            f"{base}/{ig_id}/media_publish",
            params={**params, "creation_id": creation_id},
        )
        if not r_pub.is_success:
            logger.warning("meta.instagram.publish_failed", body=r_pub.text)
        r_pub.raise_for_status()
        media_id = str(r_pub.json().get("id", ""))

        permalink = f"https://www.instagram.com/p/{media_id}/"
        r_link = client.get(
            f"{base}/{media_id}",
            params={**params, "fields": "permalink,shortcode"},
        )
        if r_link.is_success:
            data = r_link.json()
            permalink = data.get("permalink") or permalink

        logger.info("meta.instagram.published", media_id=media_id, content_format=content_format)
        return {
            "status": "published",
            "publication_url": permalink,
            "platform_post_id": media_id,
            "content_format": content_format,
        }


def _wait_meta_container_ready(client, base: str, creation_id: str, params: dict, *, max_wait_s: int = 60) -> None:
    """Espera a que Meta termine de procesar la imagen (status_code=FINISHED) antes de publicar."""
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        r = client.get(
            f"{base}/{creation_id}",
            params={**params, "fields": "status_code"},
        )
        if r.is_success:
            status = (r.json().get("status_code") or "").upper()
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise ValueError(f"Meta IG: contenedor en ERROR — {r.text[:300]}")
        time.sleep(2)
    raise ValueError("Meta IG: timeout esperando que la imagen esté lista (status_code=FINISHED)")


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock(
    platform: str,
    copy_text: str,
    image_url: str,
    idempotency_key: str | None,
    content_format: str,
) -> dict:
    """Simula publicación con URL y id determinísticos (desarrollo sin APIs reales)."""
    raw = f"{platform}:{copy_text}:{image_url}:{idempotency_key or ''}:{content_format}"
    post_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
    kind = "stories" if content_format == "story" else "posts"
    return {
        "status": f"mock_published@{datetime.now(timezone.utc).isoformat()}",
        "publication_url": f"https://social.mock/{platform}/{kind}/{post_id}",
        "platform_post_id": post_id,
        "content_format": content_format,
    }


# ---------------------------------------------------------------------------
# LinkedIn — API versionada: /rest/images (initializeUpload) + /rest/posts
# Docs: https://learn.microsoft.com/linkedin/marketing/community-management/shares/images-api
# Reemplaza a /v2/assets?action=registerUpload + /v2/ugcPosts (deprecados).
# ---------------------------------------------------------------------------

_LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"


def _linkedin_headers(token: str) -> dict:
    """Headers obligatorios de la API versionada de LinkedIn."""
    from gateway.app.core.settings import get_settings
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "LinkedIn-Version": get_settings().linkedin_api_version,
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _linkedin(
    copy_text: str,
    image_url: str,
    token: str,
    person_urn: str,
    content_format: str,
) -> dict:
    """Publica en LinkedIn con imagen: initializeUpload → PUT binario → /rest/posts."""
    import httpx

    if not person_urn:
        person_urn = _linkedin_fetch_urn(token)

    headers = _linkedin_headers(token)

    with httpx.Client(timeout=60) as client:
        # 1. Descargar la imagen (el proceso la sirve o la alcanza por PUBLIC_IMAGE_BASE_URL)
        img_resp = client.get(image_url)
        img_resp.raise_for_status()
        image_bytes = img_resp.content
        content_type = img_resp.headers.get("content-type", "image/jpeg")

        # 2. Registrar el upload y obtener URL firmada + URN del asset
        r_init = client.post(
            f"{_LINKEDIN_REST_BASE}/images?action=initializeUpload",
            json={"initializeUploadRequest": {"owner": person_urn}},
            headers=headers,
        )
        _raise_linkedin_error(r_init, "initializeUpload")
        value = r_init.json().get("value", {})
        upload_url = value.get("uploadUrl", "")
        image_urn = value.get("image", "")
        if not upload_url or not image_urn:
            raise ValueError(f"LinkedIn: initializeUpload sin uploadUrl o image URN — {r_init.text[:300]}")

        # 3. Subir los bytes al endpoint firmado
        r_upload = client.put(
            upload_url,
            content=image_bytes,
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        )
        _raise_linkedin_error(r_upload, "upload binario")

        # 4. Crear el post referenciando el asset
        post_body = {
            "author": person_urn,
            "commentary": copy_text[:3000],
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "content": {"media": {"id": image_urn, "altText": "Imagen generada por Marketing DEPA IA"}},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        r_post = client.post(f"{_LINKEDIN_REST_BASE}/posts", json=post_body, headers=headers)
        _raise_linkedin_error(r_post, "crear post")

        # El URN del share llega en el header; el body viene vacío en 201.
        post_id = r_post.headers.get("x-restli-id", "")
        if not post_id:
            post_id = str((r_post.json() or {}).get("id", "unknown")) if r_post.content else "unknown"

        logger.info("linkedin.published_with_image", post_id=post_id, asset=image_urn)
        return {
            "status": "published",
            "publication_url": f"https://www.linkedin.com/feed/update/{post_id}/",
            "platform_post_id": str(post_id),
            "content_format": content_format,
        }


def _raise_linkedin_error(resp, step: str) -> None:
    """Falla con el cuerpo de LinkedIn incluido: sus errores traen el motivo real del rechazo."""
    if resp.status_code < 400:
        return
    logger.warning("linkedin.step_failed", step=step, status=resp.status_code, body=resp.text[:500])
    raise ValueError(f"LinkedIn {step} HTTP {resp.status_code}: {resp.text[:300]}")


def _linkedin_fetch_urn(token: str) -> str:
    """Obtiene el URN del miembro autenticado vía OpenID userinfo (fallback /v2/me)."""
    import httpx
    with httpx.Client(timeout=10) as client:
        # /v2/me exige r_liteprofile, que ya no pedimos; userinfo va con el scope `profile`.
        r = client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.is_success and r.json().get("sub"):
            return f"urn:li:person:{r.json()['sub']}"
        r_me = client.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        r_me.raise_for_status()
        return f"urn:li:person:{r_me.json()['id']}"


# ---------------------------------------------------------------------------
# X (Twitter) — media upload v1.1 + create tweet v2 (OAuth 1.0a user context)
# Docs: https://developer.x.com/en/docs/twitter-api/tweets/manage-tweets/api-reference/post-tweets
# ---------------------------------------------------------------------------

def _x_oauth1_auth_header(
    method: str,
    url: str,
    *,
    access_token: str,
    access_token_secret: str,
    body: str | None = None,
    content_type: str | None = None,
) -> dict[str, str]:
    """Firma OAuth 1.0a con Consumer Keys del .env + token de usuario."""
    from oauthlib.oauth1 import Client as OAuth1Client

    from gateway.app.core.settings import get_settings

    s = get_settings()
    client = OAuth1Client(
        client_key=(s.x_api_key or "").strip(),
        client_secret=(s.x_api_secret or "").strip(),
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
        signature_type="AUTH_HEADER",
    )
    headers: dict[str, str] = {}
    if content_type:
        headers["Content-Type"] = content_type
    _uri, signed_headers, _body = client.sign(
        url,
        http_method=method,
        body=body,
        headers=headers or None,
    )
    return {k: v for k, v in dict(signed_headers).items() if k.lower() == "authorization"}


def _x_twitter(
    copy_text: str,
    image_url: str,
    access_token: str,
    access_token_secret: str,
    content_format: str,
) -> dict:
    """Publica en X: descarga imagen → upload.twitter.com → POST /2/tweets."""
    import httpx

    text = (copy_text or "").strip()[:280]
    if not text and not image_url:
        raise ValueError("X: se necesita texto o imagen para publicar")

    with httpx.Client(timeout=60) as client:
        media_id: str | None = None
        if image_url:
            img_resp = client.get(image_url)
            img_resp.raise_for_status()
            image_bytes = img_resp.content
            content_type = (img_resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
            upload_url = "https://upload.twitter.com/1.1/media/upload.json"
            auth = _x_oauth1_auth_header(
                "POST",
                upload_url,
                access_token=access_token,
                access_token_secret=access_token_secret,
            )
            # Multipart: firmar sin body (Twitter espera solo params OAuth en el header).
            r_up = client.post(
                upload_url,
                headers=auth,
                files={"media": ("image", image_bytes, content_type)},
            )
            if not r_up.is_success:
                logger.warning("x.media_upload_failed", status=r_up.status_code, body=r_up.text[:400])
                raise ValueError(f"X media upload HTTP {r_up.status_code}: {r_up.text[:300]}")
            media_id = str(r_up.json().get("media_id_string") or r_up.json().get("media_id") or "")
            if not media_id:
                raise ValueError(f"X media upload sin media_id: {r_up.text[:300]}")

        tweet_url = "https://api.twitter.com/2/tweets"
        payload: dict = {}
        if text:
            payload["text"] = text
        if media_id:
            payload["media"] = {"media_ids": [media_id]}
        import json as _json

        body = _json.dumps(payload)
        # OAuth 1.0a de X: firmar solo la URL (sin body JSON; no usan oauth_body_hash).
        auth = _x_oauth1_auth_header(
            "POST",
            tweet_url,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        r_tw = client.post(
            tweet_url,
            content=body,
            headers={**auth, "Content-Type": "application/json"},
        )
        if not r_tw.is_success:
            logger.warning("x.tweet_failed", status=r_tw.status_code, body=r_tw.text[:400])
            raise ValueError(f"X crear tweet HTTP {r_tw.status_code}: {r_tw.text[:300]}")
        tweet_id = str((r_tw.json().get("data") or {}).get("id") or "")
        if not tweet_id:
            raise ValueError(f"X respuesta sin id de tweet: {r_tw.text[:300]}")

        logger.info("x.published", tweet_id=tweet_id, content_format=content_format)
        return {
            "status": "published",
            "publication_url": f"https://x.com/i/web/status/{tweet_id}",
            "platform_post_id": tweet_id,
            "content_format": content_format,
        }
