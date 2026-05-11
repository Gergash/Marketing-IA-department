"""Migraciones ligeras para desarrollo (sin Alembic)."""

from sqlalchemy import Engine, text


def apply_lightweight_migrations(engine: Engine) -> None:
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
