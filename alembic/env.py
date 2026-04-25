import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importamos Base y los modelos para que Alembic los detecte en metadata.
from gateway.app.db.session import Base
import gateway.app.models  # noqa: F401 — registra todos los modelos en Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    """Lee DATABASE_URL del entorno o del .env; falla explícitamente si no está."""
    url = os.getenv("DATABASE_URL")
    if not url:
        from gateway.app.core.settings import get_settings
        url = get_settings().database_url
    return url


def run_migrations_offline() -> None:
    url = _db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _db_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
