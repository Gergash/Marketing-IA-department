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
        elif dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE briefs ADD COLUMN IF NOT EXISTS idioma VARCHAR(16) NOT NULL DEFAULT 'es'"
                )
            )
