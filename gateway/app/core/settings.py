from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    # LLM — provider: anthropic | openai
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Image generation — provider: mock | openai | canva
    image_provider: str = "mock"
    canva_client_id: str = ""
    canva_client_secret: str = ""
    canva_template_id: str = ""

    # Social publishing — provider: mock | linkedin | uploadpost
    social_provider: str = "mock"
    linkedin_access_token: str = ""
    linkedin_person_urn: str = ""  # optional: auto-fetched from /v2/me if blank
    uploadpost_api_key: str = ""

    # Go microservice (social publisher sidecar)
    go_publisher_url: str = "http://localhost:8088"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
