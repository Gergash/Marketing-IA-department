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
    # Mantiene el modelo cargado entre runs: sin esto Ollama lo descarga tras ~5 min
    # inactivo y el cold-start vuelve a superar el timeout → agentes al stub
    ollama_keep_alive: str = "30m"
    # Timeout de la llamada al LLM; debe tolerar la carga inicial del modelo (~5GB)
    llm_timeout_seconds: int = 300

    # Image generation — provider: stable_diffusion | comfyui | fal | venice | openai | canva | mock
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
    # Venice.ai — IMAGE_PROVIDER=venice | VIDEO_SCENE_PROVIDER=venice
    # Key: https://venice.ai/token — base real: https://api.venice.ai/api/v1
    venice_api_key: str = ""
    venice_api_base: str = "https://api.venice.ai/api/v1"
    # Imagen: venice-sd35 (pixel ≤1280) | nano-banana-pro / nano-banana-2 (aspect+resolution)
    venice_image_model: str = "venice-sd35"
    venice_image_style_preset: str = ""
    # Solo modelos resolution-tier (Nano Banana / GPT Image): 1K | 2K | 4K
    venice_image_resolution: str = "2K"
    # Animación / generación de video Venice
    # video_gen_mode: full = un clip AI | scenes = unir tomas AI | still = stills+Ken Burns
    video_gen_mode: str = "scenes"
    # Compat legacy: still | venice (si venice y mode vacío → scenes)
    video_scene_provider: str = "venice"
    # Alias: seedance-2.5 | seedance-2.0 | kling-o3 | kling-o3-pro | minimax-h3
    venice_video_model: str = "seedance-2.0"
    venice_video_duration: str = "5s"  # 5s | 10s
    venice_video_resolution: str = "720p"  # 480p | 720p | 1080p

    # OCR local para manuales de marca escaneados — provider: none | paddle
    # Flujo: pypdf primero; si hay poco texto → PaddleOCR (GPU/CPU)
    ocr_provider: str = "paddle"
    ocr_lang: str = "es"
    ocr_use_gpu: bool = True
    ocr_min_text_chars: int = 40
    ocr_max_pages: int = 40
    ocr_dpi: int = 200

    # Voiceover generation — provider: elevenlabs | openai | fal | mock
    voice_provider: str = "elevenlabs"
    voice_language: str = "es"
    elevenlabs_api_key: str = ""
    # Voz multilingüe por defecto (funciona en español con el modelo eleven_multilingual_v2)
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    # fal.ai TTS (reusa fal_api_key) — modelo nativo en español; voces: ef_dora | em_alex | em_santa
    fal_tts_model: str = "fal-ai/kokoro/spanish"
    fal_tts_voice: str = "ef_dora"

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
    # Versión de la API versionada (/rest/*). LinkedIn la exige en cada request.
    linkedin_api_version: str = "202401"
    # Scopes a solicitar. Deben estar CONCEDIDOS en la pestaña Auth de la app o
    # LinkedIn rechaza el consentimiento entero. Apps sin el producto OpenID usan
    # "r_basicprofile w_member_social".
    linkedin_scopes: str = "openid profile w_member_social"

    # OAuth 2.0 — Google Drive (fuente de clips de video del usuario)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/callback/google"

    # X (Twitter) — Consumer Keys (OAuth 1.0a) + Bearer (app-only, lectura)
    # Publicar requiere conectar cuenta vía OAuth 1.0a (token+secret de usuario).
    # Callback URL en el portal debe coincidir EXACTO con X_REDIRECT_URI.
    x_api_key: str = ""
    x_api_secret: str = ""
    x_bearer_token: str = ""
    x_redirect_uri: str = "http://localhost:8000/api/auth/callback/x"

    # URL pública base para imágenes — Meta exige HTTPS accesible públicamente (ej. ngrok en dev)
    public_image_base_url: str = "http://localhost:8000"

    # TikTok Developers — verificación de URL properties (método archivo .txt)
    # El archivo debe quedar en la raíz del dominio ngrok (FastAPI :8000), p.ej.:
    #   https://TU.ngrok-free.dev/tiktokXXXX.txt  → cuerpo exacto "tiktokXXXX"
    # Opción A: TIKTOK_VERIFY_FILENAME + TIKTOK_VERIFY_CONTENT
    # Opción B: dejar el .txt en static/tiktok-verify/
    tiktok_verify_filename: str = ""
    tiktok_verify_content: str = ""

    # Seguridad — Paso 4
    # Vacío = auth desactivada (dev local). En producción, pon un valor aleatorio largo.
    api_key: str = ""
    # Slack Incoming Webhook para notificaciones human-in-the-loop
    slack_webhook_url: str = ""

    # Hilo de pensamiento de los agentes (Marketing Studio)
    thoughts_enabled: bool = True
    thoughts_ttl_seconds: int = 7200
    # Cuánto espera un agente en un checkpoint interactivo antes de seguir solo
    thoughts_checkpoint_timeout_seconds: int = 180

    # Métricas Prometheus — False en dev (incompatibilidad con FastAPI >=0.115 en algunas versiones)
    # Activar en producción con PROMETHEUS_ENABLED=true
    prometheus_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la instancia única de configuración (memoizada)."""
    return Settings()
