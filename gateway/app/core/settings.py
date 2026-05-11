"""Carga de configuración desde entorno y `.env` (pydantic-settings)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración cargada desde variables de entorno y archivo `.env` (pydantic-settings)."""

    # Core
    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./marketing.db"
    redis_url: str = "redis://localhost:6379/0"
    default_tenant_id: str = "demo-tenant"
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )

    # LLM — provider: ollama | anthropic | openai
    llm_provider: str = "ollama"
    llm_model: str = "claude-haiku-4-5-20251001"  # usado si provider=anthropic
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    # Ollama (IA local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Image generation — provider: stable_diffusion | mock | openai | canva
    image_provider: str = "stable_diffusion"
    stable_diffusion_url: str = "http://localhost:7860/sdapi/v1/txt2img"
    # Nombre exacto del checkpoint en Automatic1111 (como en el desplegable), p. ej. archivo .safetensors
    stable_diffusion_checkpoint: str = ""
    canva_client_id: str = ""
    canva_client_secret: str = ""
    canva_template_id: str = ""

    # Social publishing — provider: mock | linkedin | uploadpost | meta
    social_provider: str = "mock"
    linkedin_access_token: str = ""
    linkedin_person_urn: str = ""  # optional: auto-fetched from /v2/me if blank
    uploadpost_api_key: str = ""
    # Meta (Instagram Business / Graph API) — SOCIAL_PROVIDER=meta
    # Token: Page long-lived con permisos instagram_basic, instagram_content_publish, pages_show_list
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_page_access_token: str = ""
    instagram_business_account_id: str = ""
    graph_api_version: str = "v21.0"

    # Go microservice (social publisher sidecar)
    go_publisher_url: str = "http://localhost:8088"

    # Seguridad — Paso 4
    # Vacío = auth desactivada (dev local). En producción, pon un valor aleatorio largo.
    api_key: str = ""
    # Slack Incoming Webhook para notificaciones human-in-the-loop
    slack_webhook_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la instancia única de configuración (memoizada)."""
    return Settings()
