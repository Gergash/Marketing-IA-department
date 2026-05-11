"""Motor SQLAlchemy, fábrica de sesiones y dependencia `get_db` para FastAPI."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from gateway.app.core.settings import get_settings


class Base(DeclarativeBase):
    """Clase base declarativa SQLAlchemy para todos los modelos ORM del gateway."""

    pass


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI: abre sesión SQLAlchemy y la cierra al terminar la petición."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
