from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BriefCreate(BaseModel):
    tema: str = Field(min_length=3)
    publico_objetivo: str
    red_social: str = "instagram"
    objetivo: str
    tono_marca: str = "profesional y cercano"
    idioma: str = "es"


class BriefResponse(BriefCreate):
    id: int
    tenant_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class RunRequest(BaseModel):
    brief_id: int
    publish: bool = True
    requires_approval: bool = True
    idempotency_key: str | None = None
    # Instagram/Meta: story = historia; linkedin/uploadpost suelen publicar como post de feed
    content_format: Literal["feed", "story"] = "feed"


class RunResponse(BaseModel):
    run_id: int
    status: str
    result: dict | None = None


class JobStatusResponse(BaseModel):
    run_id: int
    status: str
    error_message: str | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None
    result: dict | None = None
    content_format: str = "feed"


class SocialPublishStatusResponse(BaseModel):
    """Estado de configuración para publicar (sin secretos)."""

    social_provider: str
    linkedin_ready: bool
    uploadpost_ready: bool
    meta_instagram_ready: bool
    hint: str = (
        "Configura SOCIAL_PROVIDER y las credenciales en .env. "
        "Instagram feed/historia requieren cuenta profesional + Graph API (meta)."
    )


class ApproveRequest(BaseModel):
    approved_by: str = "human"


class RejectRequest(BaseModel):
    reason: str = ""
    approved_by: str = "human"


class CampaignScheduleCreate(BaseModel):
    tema: str
    red_social: str = "instagram"
    objetivo: str
    cron_expr: str = "0 9 * * 1"


class CampaignScheduleResponse(CampaignScheduleCreate):
    id: int
    tenant_id: str
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True
