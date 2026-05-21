"""Integraciones de publicación en redes (mock, LinkedIn, Upload-Post, Meta/Instagram)."""

from __future__ import annotations

import hashlib
import structlog
from datetime import datetime, timezone

logger = structlog.get_logger(__name__)


def publish_post(
    platform: str,
    copy_text: str,
    image_url: str,
    idempotency_key: str | None = None,
    *,
    content_format: str = "feed",
) -> dict:
    """Enruta la publicación según `SOCIAL_PROVIDER` en settings (LinkedIn, Upload-Post, Meta/IG o mock)."""
    from gateway.app.core.settings import get_settings
    s = get_settings()
    cf = (content_format or "feed").lower()
    if cf not in ("feed", "story"):
        cf = "feed"

    if s.social_provider == "linkedin" and s.linkedin_access_token:
        if cf == "story":
            logger.warning("linkedin.story_not_supported_publishing_as_feed")
        return _linkedin(copy_text, image_url, s.linkedin_access_token, s.linkedin_person_urn, content_format=cf)
    if s.social_provider == "uploadpost" and s.uploadpost_api_key:
        if cf == "story":
            logger.info(
                "uploadpost.story_requested",
                note="Si la API no soporta historias, puede publicarse como post normal.",
            )
        return _uploadpost(platform, copy_text, image_url, s.uploadpost_api_key, content_format=cf)
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
# LinkedIn UGC Posts API
# ---------------------------------------------------------------------------

def _linkedin(
    copy_text: str,
    image_url: str,
    token: str,
    person_urn: str,
    content_format: str,
) -> dict:
    """Publica un UGC Post de solo texto en LinkedIn (la imagen no se adjunta en este flujo simplificado)."""
    import httpx

    if not person_urn:
        person_urn = _linkedin_fetch_urn(token)

    body = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": copy_text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    with httpx.Client(timeout=15) as client:
        r = client.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
        )
        r.raise_for_status()
        post_id = r.headers.get("x-restli-id", r.json().get("id", "unknown"))
        logger.info("linkedin.published", post_id=post_id)
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


# ---------------------------------------------------------------------------
# Upload-Post unified social API — https://upload-post.com
# Supports LinkedIn, Instagram, Facebook, X, TikTok, YouTube via one endpoint.
# Docs: https://upload-post.com/docs/api
# ---------------------------------------------------------------------------

def _uploadpost(
    platform: str,
    copy_text: str,
    image_url: str,
    api_key: str,
    *,
    content_format: str,
) -> dict:
    """Publica vía API unificada upload-post.com (texto + media opcional por URL)."""
    import httpx

    # Platform slug mapping (Upload-Post uses lowercase platform names)
    platform_map = {
        "linkedin": "linkedin",
        "instagram": "instagram",
        "facebook": "facebook",
        "twitter": "twitter",
        "x": "twitter",
        "tiktok": "tiktok",
    }
    platform_slug = platform_map.get(platform.lower(), platform.lower())

    payload: dict = {
        "platforms": [platform_slug],
        "text": copy_text,
    }
    if image_url and not image_url.startswith("https://dummyimage.com"):
        payload["media"] = [{"url": image_url, "type": "image"}]

    with httpx.Client(timeout=30) as client:
        r = client.post(
            "https://api.upload-post.com/v1/posts",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        r.raise_for_status()
        data = r.json()
        post_id = str(data.get("id", "unknown"))
        logger.info("uploadpost.published", post_id=post_id, platform=platform_slug)
        return {
            "status": "published",
            "publication_url": data.get("url", f"https://upload-post.com/posts/{post_id}"),
            "platform_post_id": post_id,
            "content_format": content_format,
        }
