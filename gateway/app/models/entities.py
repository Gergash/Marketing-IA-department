"""Entidades persistentes: briefs, ejecuciones, assets, publicaciones y campañas programadas."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gateway.app.db.session import Base


class Brief(Base):
    """Brief de campaña: tema, audiencia, canal, objetivo y tono por tenant."""

    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    tema: Mapped[str] = mapped_column(String(255))
    publico_objetivo: Mapped[str] = mapped_column(String(255))
    red_social: Mapped[str] = mapped_column(String(80))
    objetivo: Mapped[str] = mapped_column(String(80))
    tono_marca: Mapped[str] = mapped_column(String(120), default="profesional y cercano")
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class GeneratedAsset(Base):
    """Imagen generada vinculada a un run (URL servida y prompt usado)."""

    __tablename__ = "generated_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    image_url: Mapped[str] = mapped_column(Text)
    image_prompt: Mapped[str] = mapped_column(Text)
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
    tema: Mapped[str] = mapped_column(String(255))
    red_social: Mapped[str] = mapped_column(String(80))
    objetivo: Mapped[str] = mapped_column(String(80))
    cron_expr: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
