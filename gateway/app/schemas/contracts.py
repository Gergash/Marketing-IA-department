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
    image_provider: Literal["stable_diffusion", "fal", "venice"] | None = None
    # Override manual del arquetipo visual (si None, el agente lo elige automáticamente)
    archetype_override: Literal[
        "brand_campaign_piece",
        "typographic_poster",
        "minimal_conceptual",
        "editorial_infographic",
        "cinematic_hero",
    ] | None = None
    # Foto del usuario (URL de POST /api/briefs/upload-asset)
    user_asset_url: str | None = None
    alter_image_with_ai: bool = False
    visual_instructions: str | None = None
    # Carpeta de Google Drive con los clips fuente — requerida cuando content_format=user_clip_reel
    drive_folder_id: str | None = None
    # Cuenta social destino (id de GET /api/auth/accounts). None = única cuenta del provider (legacy)
    social_account_id: int | None = None
    # Enlace a adjuntar en la descripción del post (no se pinta en la imagen)
    link_url: str | None = None
    # Si True, pinta el CTA como pastilla en la imagen (solo para remarcar info importante)
    cta_on_image: bool = False
    # Identificador del hilo de pensamiento, generado por el cliente: /runs/sync no devuelve
    # el run_id hasta terminar, así que el dashboard necesita una clave para seguir el run en vivo
    trace_id: str | None = Field(default=None, max_length=64)
    # Si True, los agentes se detienen en los checkpoints a esperar indicaciones del usuario
    interactive: bool = False
    # Reels: full = clip AI completo | scenes = unir tomas AI | still = stills+Shotstack
    video_gen_mode: Literal["full", "scenes", "still"] | None = None
    # Alias Venice: seedance-2.5 | seedance-2.0 | kling-o3 | kling-o3-pro | minimax-h3
    venice_video_model: str | None = None

    @model_validator(mode="after")
    def _require_drive_folder_for_user_clip_reel(self) -> "RunRequest":
        if self.content_format == "user_clip_reel" and not self.drive_folder_id:
            raise ValueError(
                "content_format='user_clip_reel' requiere drive_folder_id (carpeta de Google Drive con los clips)"
            )
        return self

    @model_validator(mode="after")
    def _normalize_link_url(self) -> "RunRequest":
        if self.link_url is not None:
            cleaned = self.link_url.strip()
            self.link_url = cleaned or None
        return self


class UploadAssetResponse(BaseModel):
    """Respuesta tras subir una foto del usuario."""

    url: str
    filename: str
    content_type: str
    size_bytes: int


class BrandManualResponse(BaseModel):
    """Manual de marca PDF cargado, texto OCR y escaneo visual completo."""

    id: str
    url: str
    original_filename: str
    char_count: int
    text_preview: str = ""
    extraction_method: str = ""
    palette_hex: list[str] = Field(default_factory=list)
    color_roles: dict[str, str] = Field(default_factory=dict)
    logo_urls: list[str] = Field(default_factory=list)
    logo_placements: list[str] = Field(default_factory=list)
    font_names: list[str] = Field(default_factory=list)
    layout_hints: list[str] = Field(default_factory=list)
    suggested_archetype: str | None = None
    pages_scanned: int = 0
    embedded_images: int = 0


class AdvisorChatRequest(BaseModel):
    """Mensaje al asesor creativo (burbuja)."""

    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)
    brief_context: dict | None = None


class AdvisorChatResponse(BaseModel):
    """Respuesta del asesor creativo."""

    reply: str


class ImageProvidersResponse(BaseModel):
    """Proveedores de imagen disponibles según configuración del servidor."""

    default_provider: str
    providers: list[dict[str, str]]


class VideoOptionsResponse(BaseModel):
    """Opciones de generación de video (Venice) expuestas al frontend."""

    default_mode: str
    default_model: str
    modes: list[dict[str, str]]
    models: list[dict[str, str]]
    venice_configured: bool


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


class ThoughtEvent(BaseModel):
    """Un latido del hilo de pensamiento: qué agente habla, en qué fase y con qué datos."""

    id: str
    trace_id: str
    ts: str
    agent: str
    agent_label: str
    # start | thinking | output | question | answer | error | end
    phase: str
    message: str
    data: dict = Field(default_factory=dict)
    checkpoint: str | None = None
    options: list[dict] = Field(default_factory=list)


class ThoughtsResponse(BaseModel):
    """Ventana de eventos del hilo; `next_since` alimenta el siguiente poll."""

    trace_id: str
    events: list[ThoughtEvent] = Field(default_factory=list)
    next_since: int = 0
    interactive_supported: bool = True


class ThoughtReplyRequest(BaseModel):
    """Respuesta del usuario al agente que espera en un checkpoint."""

    action: Literal["continue", "adjust", "cancel"] = "continue"
    notes: str = ""
    # Checkpoint al que responde; vacío = el que esté abierto en ese momento
    checkpoint: str = ""

    @model_validator(mode="after")
    def _require_notes_for_adjust(self) -> "ThoughtReplyRequest":
        if self.action == "adjust" and not self.notes.strip():
            raise ValueError("action='adjust' requiere notes con lo que quieres cambiar")
        return self


class ThoughtReplyResponse(BaseModel):
    """Confirmación de que la respuesta quedó encolada para el agente."""

    trace_id: str
    action: str
    checkpoint: str = ""
    accepted: bool = True


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


class ReviseRequest(BaseModel):
    """Notas del revisor para regenerar la pieza de un run en `pending_approval`."""

    notes: str = Field(min_length=3)
    revised_by: str = "human"
    # Hilo de pensamiento de esta regeneración (nuevo, no el del run original)
    trace_id: str | None = Field(default=None, max_length=64)
    interactive: bool = False

    @model_validator(mode="after")
    def _reject_blank_notes(self) -> "ReviseRequest":
        if not self.notes.strip():
            raise ValueError("notes no puede ser solo espacios en blanco")
        return self


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
