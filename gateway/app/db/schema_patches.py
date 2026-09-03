"""Migraciones ligeras para desarrollo (sin Alembic)."""

from sqlalchemy import Engine, text

_CREATE_OAUTH_TOKENS_SQLITE = """
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   VARCHAR(64)  NOT NULL,
    provider    VARCHAR(32)  NOT NULL,
    access_token TEXT        NOT NULL,
    refresh_token TEXT,
    expires_at  DATETIME,
    account_id  VARCHAR(256) NOT NULL DEFAULT '',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_OAUTH_TOKENS_PG = """
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id            SERIAL PRIMARY KEY,
    tenant_id     VARCHAR(64)  NOT NULL,
    provider      VARCHAR(32)  NOT NULL,
    access_token  TEXT         NOT NULL,
    refresh_token TEXT,
    expires_at    TIMESTAMP,
    account_id    VARCHAR(256) NOT NULL DEFAULT '',
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP    NOT NULL DEFAULT NOW()
)
"""


def apply_lightweight_migrations(engine: Engine) -> None:
    """Añade columnas y tablas faltantes en SQLite/Postgres sin migración Alembic (solo desarrollo / parches)."""
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            rows = conn.execute(text("PRAGMA table_info(briefs)")).fetchall()
            if not rows:
                return
            cols = {r[1] for r in rows}
            if "idioma" not in cols:
                conn.execute(text("ALTER TABLE briefs ADD COLUMN idioma VARCHAR(16) DEFAULT 'es'"))
            rows_ar = conn.execute(text("PRAGMA table_info(agent_runs)")).fetchall()
            if rows_ar:
                cols_ar = {r[1] for r in rows_ar}
                if "content_format" not in cols_ar:
                    conn.execute(
                        text("ALTER TABLE agent_runs ADD COLUMN content_format VARCHAR(16) DEFAULT 'feed'")
                    )
                if "run_params_json" not in cols_ar:
                    conn.execute(text("ALTER TABLE agent_runs ADD COLUMN run_params_json TEXT"))
                if "revision_notes" not in cols_ar:
                    conn.execute(text("ALTER TABLE agent_runs ADD COLUMN revision_notes TEXT"))
                if "revision_count" not in cols_ar:
                    conn.execute(
                        text("ALTER TABLE agent_runs ADD COLUMN revision_count INTEGER DEFAULT 0")
                    )
            conn.execute(text(_CREATE_OAUTH_TOKENS_SQLITE))
            conn.execute(
                text(
                    """
CREATE TABLE IF NOT EXISTS app_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash VARCHAR(512) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL UNIQUE,
    full_name VARCHAR(256) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
                )
            )
            conn.execute(
                text(
                    """
CREATE TABLE IF NOT EXISTS credit_wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id VARCHAR(64) NOT NULL UNIQUE,
    balance INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
                )
            )
            conn.execute(
                text(
                    """
CREATE TABLE IF NOT EXISTS payment_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id VARCHAR(64) NOT NULL,
    reference VARCHAR(128) NOT NULL UNIQUE,
    provider VARCHAR(32) NOT NULL DEFAULT 'bold',
    amount_cop INTEGER NOT NULL DEFAULT 0,
    credits_added INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    payer_email VARCHAR(320),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
                )
            )
        elif dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE briefs ADD COLUMN IF NOT EXISTS idioma VARCHAR(16) NOT NULL DEFAULT 'es'"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS content_format VARCHAR(16) NOT NULL DEFAULT 'feed'"
                )
            )
            conn.execute(text("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS run_params_json TEXT"))
            conn.execute(text("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS revision_notes TEXT"))
            conn.execute(
                text(
                    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS revision_count INTEGER NOT NULL DEFAULT 0"
                )
            )
            conn.execute(text(_CREATE_OAUTH_TOKENS_PG))
            conn.execute(
                text(
                    """
CREATE TABLE IF NOT EXISTS app_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash VARCHAR(512) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL UNIQUE,
    full_name VARCHAR(256) NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""
                )
            )
            conn.execute(
                text(
                    """
CREATE TABLE IF NOT EXISTS credit_wallets (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL UNIQUE,
    balance INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""
                )
            )
            conn.execute(
                text(
                    """
CREATE TABLE IF NOT EXISTS payment_records (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    reference VARCHAR(128) NOT NULL UNIQUE,
    provider VARCHAR(32) NOT NULL DEFAULT 'bold',
    amount_cop INTEGER NOT NULL DEFAULT 0,
    credits_added INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    payer_email VARCHAR(320),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""
                )
            )
