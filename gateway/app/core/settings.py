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

    # Image generation — provider: stable_diffusion | comfyui | fal | openai | canva | mock
    image_provider: str = "stable_diffusion"
    stable_diffusion_url: str = "http://localhost:7860/sdapi/v1/txt2img"
    # Nombre exacto del checkpoint en Automatic1111 (como en el desplegable), p. ej. archivo .safetensors
    stable_diffusion_checkpoint: str = ""
    canva_client_id: str = ""
    canva_client_secret: str = ""
    canva_template_id: str = ""
    # fal.ai (Flux pro vía API) — IMAGE_PROVIDER=fal
    fal_api_key: str = ""
    # Modelo fal a usar; opciones: fal-ai/flux-pro/v1.1 | fal-ai/flux/schnell | fal-ai/recraft-v3
    fal_model: str = "fal-ai/flux-pro/v1.1"
    # Modelo img2img cuando el usuario sube foto y pide alteración con IA
    fal_img2img_model: str = "fal-ai/flux/dev/image-to-image"
    fal_img2img_strength: float = 0.72

    # Voiceover generation — provider: elevenlabs | openai | mock
    voice_provider: str = "elevenlabs"
    voice_language: str = "es"
    elevenlabs_api_key: str = ""
    # Voz multilingüe por defecto (funciona en español con el modelo eleven_multilingual_v2)
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"

    # Transcripción de audio (clips de usuario) — provider: whisper | mock
    stt_provider: str = "whisper"

    # Efecto visual generativo opcional sobre el segmento hook de user_clip_reel — fal.ai wan-effects
    effects_enabled: bool = False
    fal_effects_model: str = "fal-ai/wan-effects"

    # Video rendering (Reels) — provider: shotstack | json2video | mock
    video_provider: str = "shotstack"
    shotstack_api_key: str = ""
    shotstack_env: str = "stage"  # stage | v1 (produccion)
    json2video_api_key: str = ""  # alternativa documentada, no implementada en v1
    video_max_wait_seconds: int = 600
    video_fps: int = 30

    # Social publishing — provider: mock | linkedin | meta
    social_provider: str = "mock"
    linkedin_access_token: str = ""
    linkedin_person_urn: str = ""  # optional: auto-fetched from /v2/me if blank
    # Meta (Instagram Business / Graph API) — SOCIAL_PROVIDER=meta
    # Token: Page long-lived con permisos instagram_basic, instagram_content_publish, pages_show_list
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_facebook_page_id: str = ""  # Fan Page ID (no confundir con meta_app_id)
    meta_page_access_token: str = ""
    instagram_business_account_id: str = ""
    graph_api_version: str = "v21.0"

    # Go microservice (social publisher sidecar)
    go_publisher_url: str = "http://localhost:8088"

    # OAuth 2.0 — Meta (Facebook/Instagram Graph API)
    meta_client_id: str = ""
    meta_client_secret: str = ""
    meta_redirect_uri: str = "http://localhost:8000/api/auth/callback/meta"
    oauth_success_redirect_url: str = "http://localhost:5173/"

    # OAuth 2.0 — LinkedIn
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8000/api/auth/callback/linkedin"

    # OAuth 2.0 — Google Drive (fuente de clips de video del usuario)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/callback/google"

    # URL pública base para imágenes — Meta exige HTTPS accesible públicamente (ej. ngrok en dev)
    public_image_base_url: str = "http://localhost:8000"

    # Seguridad — Paso 4
    # Vacío = auth desactivada (dev local). En producción, pon un valor aleatorio largo.
    api_key: str = ""
    # Slack Incoming Webhook para notificaciones human-in-the-loop
    slack_webhook_url: str = ""

    # Métricas Prometheus — False en dev (incompatibilidad con FastAPI >=0.115 en algunas versiones)
    # Activar en producción con PROMETHEUS_ENABLED=true
    prometheus_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la instancia única de configuración (memoizada)."""
    return Settings()
