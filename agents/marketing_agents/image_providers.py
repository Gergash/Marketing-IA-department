from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Social media landscape format: 1792x1024 (16:9) for feed posts.
_IMAGE_SIZE = "1792x1024"


def generate_image(prompt: str) -> str:
    """Return a public image URL for the given prompt."""
    from gateway.app.core.settings import get_settings
    s = get_settings()

    if s.image_provider == "openai" and s.openai_api_key:
        return _dalle(prompt, s.openai_api_key)
    if s.image_provider == "canva":
        return _canva(prompt, s)
    return _placeholder(prompt)


def _dalle(prompt: str, api_key: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt[:4000],
            size=_IMAGE_SIZE,
            quality="standard",
            n=1,
        )
        url = resp.data[0].url
        logger.info("image.dalle_generated", url=url[:80] if url else "")
        return url or _placeholder(prompt)
    except Exception as exc:
        logger.error("image.dalle_error", error=str(exc))
        return _placeholder(prompt)


def _canva(prompt: str, settings) -> str:
    # Canva Connect API requires OAuth 2.0 + brand template ID.
    # Steps to enable:
    #   1. Create an app at https://www.canva.com/developers
    #   2. Set CANVA_CLIENT_ID, CANVA_CLIENT_SECRET in .env
    #   3. Configure a brand template and set CANVA_TEMPLATE_ID
    #   4. Implement OAuth flow (POST /v1/oauth/token) to get access token
    #   5. POST /v1/designs with brandTemplateId and data_fields to inject content
    # Until configured, falls back to placeholder.
    if not settings.canva_client_id:
        logger.warning("image.canva_not_configured")
        return _placeholder(prompt)

    logger.warning("image.canva_oauth_not_implemented")
    return _placeholder(prompt)


def _placeholder(prompt: str) -> str:
    text = prompt[:50].replace(" ", "+")
    return f"https://dummyimage.com/1792x1024/1a202c/ffffff&text={text}"
