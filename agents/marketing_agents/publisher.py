import hashlib
from datetime import datetime, timezone

from .schemas import CopyOutput, DesignOutput, PublishOutput


class PublisherAgent:
    def run(
        self,
        platform: str,
        copy: CopyOutput,
        design: DesignOutput,
        idempotency_key: str | None = None,
    ) -> PublishOutput:
        raw_id = f"{platform}:{copy.copy_final}:{design.image_url}:{idempotency_key or ''}"
        post_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]
        publication_url = f"https://social.mock/{platform}/posts/{post_id}"
        return PublishOutput(
            status=f"published@{datetime.now(timezone.utc).isoformat()}",
            publication_url=publication_url,
            platform_post_id=post_id,
        )
