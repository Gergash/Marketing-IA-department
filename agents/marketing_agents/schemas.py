from pydantic import BaseModel, Field


class BriefInput(BaseModel):
    """Entrada del pipeline de agentes: mismo significado que el brief persistido en API."""

    tema: str = Field(min_length=3)
    publico_objetivo: str
    red_social: str
    objetivo: str
    tono_marca: str = "profesional y cercano"
    idioma: str = "es"
    # Extracto del manual de marca (PDF) — no se persiste en la tabla briefs
    brand_context: str = ""
    # Escaneo visual del PDF (paleta + logos) — no se persiste en briefs
    brand_palette: list[str] = Field(default_factory=list)
    brand_logo_urls: list[str] = Field(default_factory=list)
    brand_logo_paths: list[str] = Field(default_factory=list)
    tenant_id: str = ""


class StrategyOutput(BaseModel):
    """Salida del estratega: tipo de post, hook, mensaje y hashtags sugeridos."""

    tipo_post: str
    hook: str
    mensaje_base: str
    hashtags: list[str]


class CopyOutput(BaseModel):
    """Texto publicable, hashtags finales y llamada a la acción."""

    copy_final: str
    hashtags: list[str]
    cta: str
    # Texto corto para overlay en imagen (oraciones completas, ortografía correcta)
    headline_for_image: str = ""
    subline_for_image: str = ""


class DesignOutput(BaseModel):
    """URL de la imagen generada y el prompt visual usado."""

    image_url: str
    image_prompt: str
    image_provider: str = ""
    image_width: int = 0
    image_height: int = 0
    content_format: str = "feed"
    layout_archetype: str = ""
    layout_label: str = ""
    color_palette: str = ""
    design_source: str = "generated"  # generated | user_overlay | user_img2img


class VideoDesignOutput(BaseModel):
    """Salida del diseñador de video: URL del reel renderizado, sibling de `DesignOutput` para content_format=reel."""

    image_url: str | None = None
    video_url: str = ""
    video_prompt: str = ""
    video_provider: str = ""
    voice_provider: str = ""
    width: int = 0
    height: int = 0
    duration_s: float = 0.0
    scene_count: int = 0
    layout_archetype: str = ""


class PublishOutput(BaseModel):
    """Respuesta unificada del publicador (estado, enlaces e id externo)."""

    status: str
    publication_url: str
    platform_post_id: str
    content_format: str = "feed"
    provider: str = ""
    platforms: list[str] = Field(default_factory=list)
    platform_results: list[dict] = Field(default_factory=list)
    request_id: str = ""
