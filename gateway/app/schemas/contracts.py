"""Modelos Pydantic de entrada/salida de la API REST (briefs, runs, campañas, redes)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class ArchetypeInfo(BaseModel):
    """Arquetipo de layout editorial disponible para override manual."""

    id: str
    label: str


class RunRequest(BaseModel):
    """Solicitud de ejecución del pipeline: brief, flags de publicación/aprobación y formato feed/story."""

    brief_id: int
    publish: bool = True
    requires_approval: bool = True
    idempotency_key: str | None = None
    # Instagram/Meta: story = historia; reel = video corto vertical generado con IA (solo async);
    # user_clip_reel = reel armado con clips reales del usuario desde Google Drive (solo async);
    # linkedin suele publicar como post de feed
    content_format: Literal["feed", "story", "reel", "user_clip_reel"] = "feed"
    # Override del generador de imagen por run (si None, usa IMAGE_PROVIDER del .env)
    image_provider: Literal["stable_diffusion", "fal"] | None = None
    # Override manual del arquetipo visual (si None, el agente lo elige automáticamente)
    archetype_override: Literal[
        "typographic_poster", "minimal_conceptual", "editorial_infographic", "cinematic_hero"
    ] | None = None
    # Foto del usuario (URL de POST /api/briefs/upload-asset)
    user_asset_url: str | None = None
    alter_image_with_ai: bool = False
    visual_instructions: str | None = None
    # Carpeta de Google Drive con los clips fuente — requerida cuando content_format=user_clip_reel
    drive_folder_id: str | None = None

    @model_validator(mode="after")
    def _require_drive_folder_for_user_clip_reel(self) -> "RunRequest":
        if self.content_format == "user_clip_reel" and not self.drive_folder_id:
            raise ValueError(
                "content_format='user_clip_reel' requiere drive_folder_id (carpeta de Google Drive con los clips)"
            )
        return self


class UploadAssetResponse(BaseModel):
    """Respuesta tras subir una foto del usuario."""

    url: str
    filename: str
    content_type: str
    size_bytes: int


class ImageProvidersResponse(BaseModel):
    """Proveedores de imagen disponibles según configuración del servidor."""

    default_provider: str
    providers: list[dict[str, str]]


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
    linkedin_oauth_connected: bool = False
    meta_oauth_connected: bool = False
    meta_instagram_ready: bool
    go_publisher_url: str = "http://localhost:8088"
    hint: str = (
        "Configura SOCIAL_PROVIDER y las credenciales en .env. "
        "LinkedIn nativo: conecta con OAuth en el dashboard y usa SOCIAL_PROVIDER=meta o brief red_social=linkedin. "
        "Instagram/Facebook: meta + Go sidecar en :8088."
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
