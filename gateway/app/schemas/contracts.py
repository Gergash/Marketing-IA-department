"""Modelos Pydantic de entrada/salida de la API REST (briefs, runs, campañas, redes)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BriefCreate(BaseModel):
    """Cuerpo POST para crear un brief de campaña."""

    tema: str = Field(min_length=3)
    publico_objetivo: str
    red_social: str = "instagram"
    objetivo: str
    tono_marca: str = "profesional y cercano"
    idioma: str = "es"


class BriefResponse(BriefCreate):
    """Brief persistido con id, tenant y marca de tiempo."""

    id: int
    tenant_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class RunRequest(BaseModel):
    """Solicitud de ejecución del pipeline: brief, flags de publicación/aprobación y formato feed/story."""

    brief_id: int
    publish: bool = True
    requires_approval: bool = True
    idempotency_key: str | None = None
    # Instagram/Meta: story = historia; linkedin/uploadpost suelen publicar como post de feed
    content_format: Literal["feed", "story"] = "feed"


class RunResponse(BaseModel):
    """Respuesta inmediata tras sync o async: id de run, estado y resultado si aplica."""

    run_id: int
    status: str
    result: dict | None = None


class JobStatusResponse(BaseModel):
    """Estado detallado de un run para listados y consulta por id."""

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
    """Metadatos opcionales al aprobar un run (quién aprueba)."""

    approved_by: str = "human"


class RejectRequest(BaseModel):
    """Motivo y autor al rechazar un run pendiente."""

    reason: str = ""
    approved_by: str = "human"


class CampaignScheduleCreate(BaseModel):
    """Definición de campaña recurrente (cron) sin id de base de datos."""

    tema: str
    red_social: str = "instagram"
    objetivo: str
    cron_expr: str = "0 9 * * 1"


class CampaignScheduleResponse(CampaignScheduleCreate):
    """Campaña programada almacenada con id, tenant, flag enabled y fecha de creación."""

    id: int
    tenant_id: str
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CampaignFireResponse(BaseModel):
    """Resultado de disparar una campaña manualmente (prueba de fuego del scheduler)."""

    campaign_id: int
    run_id: int
    status: str
    message: str = "Pipeline ejecutado; revisa pending_approval en dashboard o GET /api/runs"
