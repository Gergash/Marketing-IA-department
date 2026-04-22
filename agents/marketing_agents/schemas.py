from pydantic import BaseModel, Field


class BriefInput(BaseModel):
    tema: str = Field(min_length=3)
    publico_objetivo: str
    red_social: str
    objetivo: str
    tono_marca: str = "profesional y cercano"
    idioma: str = "es"


class StrategyOutput(BaseModel):
    tipo_post: str
    hook: str
    mensaje_base: str
    hashtags: list[str]


class CopyOutput(BaseModel):
    copy_final: str
    hashtags: list[str]
    cta: str


class DesignOutput(BaseModel):
    image_url: str
    image_prompt: str


class PublishOutput(BaseModel):
    status: str
    publication_url: str
    platform_post_id: str
