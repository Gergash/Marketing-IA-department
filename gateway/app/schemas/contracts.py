from datetime import datetime

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
