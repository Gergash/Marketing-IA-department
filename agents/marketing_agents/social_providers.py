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
) -> dict:
    """Route to the configured social provider. Returns publish result dict."""
    from gateway.app.core.settings import get_settings
    s = get_settings()

    if s.social_provider == "linkedin" and s.linkedin_access_token:
        return _linkedin(copy_text, image_url, s.linkedin_access_token, s.linkedin_person_urn)
    if s.social_provider == "uploadpost" and s.uploadpost_api_key:
        return _uploadpost(platform, copy_text, image_url, s.uploadpost_api_key)
    return _mock(platform, copy_text, image_url, idempotency_key)


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock(
    platform: str,
    copy_text: str,
    image_url: str,
    idempotency_key: str | None,
) -> dict:
    raw = f"{platform}:{copy_text}:{image_url}:{idempotency_key or ''}"
    post_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return {
        "status": f"mock_published@{datetime.now(timezone.utc).isoformat()}",
        "publication_url": f"https://social.mock/{platform}/posts/{post_id}",
        "platform_post_id": post_id,
    }


# ---------------------------------------------------------------------------
# LinkedIn UGC Posts API
# ---------------------------------------------------------------------------

def _linkedin(
    copy_text: str,
    image_url: str,
    token: str,
    person_urn: str,
) -> dict:
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
        }


def _linkedin_fetch_urn(token: str) -> str:
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
) -> dict:
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
        }
