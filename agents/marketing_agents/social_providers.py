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
) -> dict:
    """Enruta la publicación según plataforma y tokens disponibles (LinkedIn, Meta/IG o mock)."""
    from gateway.app.core.settings import get_settings
    s = get_settings()
    cf = (content_format or "feed").lower()
    if cf not in ("feed", "story"):
        cf = "feed"

    if platform.lower() in ("linkedin",) and linkedin_token:
        return _linkedin(copy_text, image_url, linkedin_token, linkedin_urn or "", content_format=cf)
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
# LinkedIn UGC Posts API — publicación con imagen vía registerUpload
# ---------------------------------------------------------------------------

def _linkedin(
    copy_text: str,
    image_url: str,
    token: str,
    person_urn: str,
    content_format: str,
) -> dict:
    """Publica en LinkedIn con imagen vía UGC Posts API (registerUpload → PUT → ugcPosts)."""
    import httpx

    if not person_urn:
        person_urn = _linkedin_fetch_urn(token)

    headers_auth = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    with httpx.Client(timeout=60) as client:
        # 1. Descargar imagen (localhost es accesible desde el mismo proceso)
        img_resp = client.get(image_url)
        img_resp.raise_for_status()
        image_bytes = img_resp.content
        content_type = img_resp.headers.get("content-type", "image/jpeg")

        # 2. Registrar upload en LinkedIn
        register_body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": person_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }
        r_register = client.post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            json=register_body,
            headers=headers_auth,
        )
        r_register.raise_for_status()
        value = r_register.json().get("value", {})
        upload_mechanism = value.get("uploadMechanism", {}).get(
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}
        )
        upload_url = upload_mechanism.get("uploadUrl", "")
        asset_urn = value.get("asset", "")
        if not upload_url or not asset_urn:
            raise ValueError("LinkedIn: registerUpload no devolvió uploadUrl o asset")

        # 3. Subir imagen binaria
        upload_headers = {k: v for k, v in upload_mechanism.get("headers", {}).items()}
        upload_headers["Authorization"] = f"Bearer {token}"
        upload_headers["Content-Type"] = content_type
        r_upload = client.put(upload_url, content=image_bytes, headers=upload_headers)
        r_upload.raise_for_status()

        # 4. Crear el UGC post con imagen
        post_body = {
            "author": person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": copy_text[:3000]},
                    "shareMediaCategory": "IMAGE",
                    "media": [
                        {
                            "status": "READY",
                            "description": {"text": "Imagen generada por Marketing DEPA IA"},
                            "media": asset_urn,
                            "title": {"text": ""},
                        }
                    ],
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        r_post = client.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=post_body,
            headers=headers_auth,
        )
        r_post.raise_for_status()
        post_id = r_post.headers.get("x-restli-id", r_post.json().get("id", "unknown"))
        logger.info("linkedin.published_with_image", post_id=post_id, asset=asset_urn)
        return {
            "status": "published",
            "publication_url": f"https://www.linkedin.com/feed/update/{post_id}/",
            "platform_post_id": str(post_id),
            "content_format": content_format,
        }


def _linkedin_fetch_urn(token: str) -> str:
    """Obtiene el URN `urn:li:person:{id}` del miembro autenticado para usar como autor del post."""
    import httpx
    with httpx.Client(timeout=10) as client:
        r = client.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return f"urn:li:person:{r.json()['id']}"
