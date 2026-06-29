"""Agente publicador: delega en `social_providers` según configuración."""

from .schemas import CopyOutput, DesignOutput, PublishOutput
from .social_providers import publish_post


class PublisherAgent:
    """Capa fina sobre `publish_post`: envía copy + URL de imagen al proveedor social configurado."""

    def run(
        self,
        platform: str,
        copy: CopyOutput,
        design: DesignOutput,
        idempotency_key: str | None = None,
        *,
        content_format: str = "feed",
        linkedin_token: str | None = None,
        linkedin_urn: str | None = None,
    ) -> PublishOutput:
        """Delega en `social_providers.publish_post` y empaqueta la respuesta como `PublishOutput`."""
        result = publish_post(
            platform=platform,
            copy_text=copy.copy_final,
            image_url=design.image_url,
            idempotency_key=idempotency_key,
            content_format=content_format,
            linkedin_token=linkedin_token,
            linkedin_urn=linkedin_urn,
        )
        return PublishOutput(**result)
