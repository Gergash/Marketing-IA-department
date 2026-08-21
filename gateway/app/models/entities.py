"""Entidades persistentes: briefs, ejecuciones, assets, publicaciones, campañas y tokens OAuth."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gateway.app.db.session import Base


class Brief(Base):
    """Brief de campaña: tema, audiencia, canal, objetivo y tono por tenant."""

    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    tema: Mapped[str] = mapped_column(Text)
    publico_objetivo: Mapped[str] = mapped_column(Text)
    red_social: Mapped[str] = mapped_column(String(80))
    objetivo: Mapped[str] = mapped_column(Text)
    tono_marca: Mapped[str] = mapped_column(Text, default="profesional y cercano")
    idioma: Mapped[str] = mapped_column(String(16), default="es")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    """Una ejecución del pipeline: estado, resultado JSON, idempotencia y aprobación humana."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    brief_id: Mapped[int] = mapped_column(Integer, index=True)
    run_mode: Mapped[str] = mapped_column(String(40), default="sync")
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # feed | story — Instagram/Meta; otras redes suelen ignorar o mapear a feed
    content_format: Mapped[str] = mapped_column(String(16), default="feed")
    # Human-in-the-loop: quién y cuándo aprobó (o rechazó) el run
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Cuenta social destino (oauth_tokens.id). NULL = única cuenta del provider (legacy)
    social_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Parámetros del run original (arquetipo, foto, proveedor, carpeta Drive...): sin esto
    # una revisión no puede re-ejecutar el pipeline con la misma configuración
    run_params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Notas de revisión acumuladas del dashboard y cuántas veces se regeneró la pieza
    revision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class UserAsset(Base):
    """Foto subida por el tenant: biblioteca reutilizable como capa base de diseño."""

    __tablename__ = "user_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(256))  # uuid.ext en disco
    original_filename: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GeneratedAsset(Base):
    """Imagen generada vinculada a un run (URL servida y prompt usado)."""

    __tablename__ = "generated_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    image_url: Mapped[str] = mapped_column(Text)
    image_prompt: Mapped[str] = mapped_column(Text)
    # Video renderizado (Reels); nullable porque solo se puebla en runs content_format=reel
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Publication(Base):
    """Registro de publicación en red social tras un run exitoso."""

    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(80))
    publication_url: Mapped[str] = mapped_column(Text)
    platform_post_id: Mapped[str] = mapped_column(String(128), index=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CampaignSchedule(Base):
    """Programación recurrente (expresión cron) para futuras campañas por tenant."""

    __tablename__ = "campaign_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    tema: Mapped[str] = mapped_column(Text)
    red_social: Mapped[str] = mapped_column(String(80))
    objetivo: Mapped[str] = mapped_column(Text)
    cron_expr: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OAuthToken(Base):
    """Cuenta social conectada: token OAuth 2.0 por tenant, proveedor y cuenta.

    Multi-cuenta: un tenant puede tener N filas por proveedor (una por cuenta),
    únicas por (tenant_id, provider, account_id).
    """

    __tablename__ = "oauth_tokens"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "account_id", name="uq_oauth_tenant_provider_account"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)  # 'meta' | 'linkedin' | 'google'
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    account_id: Mapped[str] = mapped_column(String(256))  # IG Business Account ID o URN de LinkedIn
    # Identidad visible en el dashboard (selector de cuenta destino)
    account_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    profile_picture_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Meta: Page de Facebook dueña de la cuenta IG (token de página va en access_token)
    page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Desconexión lógica: False oculta la cuenta sin borrar historial
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
