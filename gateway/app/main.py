from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from gateway.app.api.routes import router
from gateway.app.core.logging import configure_logging
from gateway.app.core.settings import get_settings
from gateway.app.db.session import Base, engine
from gateway.app.services.scheduler_service import start_scheduler, stop_scheduler

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Marketing DEPA IA Gateway", version="0.1.0")
_cors_list = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
Instrumentator().instrument(app).expose(app)


def _init_db() -> None:
    dialect = engine.dialect.name
    if dialect == "sqlite":
        # Dev rápido: create_all + parche de columnas (sin Alembic).
        from gateway.app.db.schema_patches import apply_lightweight_migrations
        Base.metadata.create_all(bind=engine)
        apply_lightweight_migrations(engine)
    else:
        # PostgreSQL (y cualquier otro): Alembic es la única fuente de verdad.
        # Las migraciones se aplican con: alembic upgrade head
        # En startup solo verificamos que la conexión funcione.
        with engine.connect():
            pass


@app.on_event("startup")
def on_startup() -> None:
    _init_db()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()
