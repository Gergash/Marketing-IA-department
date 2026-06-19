from pydantic import BaseModel, Field


class BriefInput(BaseModel):
    """Entrada del pipeline de agentes: mismo significado que el brief persistido en API."""

    tema: str = Field(min_length=3)
    publico_objetivo: str
    red_social: str
    objetivo: str
    tono_marca: str = "profesional y cercano"
    idioma: str = "es"


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


class PublishOutput(BaseModel):
    """Respuesta unificada del publicador (estado, enlaces e id externo)."""

    status: str
    publication_url: str
    platform_post_id: str
    content_format: str = "feed"
