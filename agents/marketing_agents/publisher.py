from .schemas import CopyOutput, DesignOutput, PublishOutput
from .social_providers import publish_post


class PublisherAgent:
    def run(
        self,
        platform: str,
        copy: CopyOutput,
        design: DesignOutput,
        idempotency_key: str | None = None,
    ) -> PublishOutput:
        result = publish_post(
            platform=platform,
            copy_text=copy.copy_final,
            image_url=design.image_url,
            idempotency_key=idempotency_key,
        )
        return PublishOutput(**result)
