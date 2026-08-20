"""Punto de entrada FastAPI: CORS, rutas, métricas Prometheus, estáticos y ciclo de vida BD/scheduler."""

from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from gateway.app.api.auth_social import router as auth_social_router
from gateway.app.api.legal import router as legal_router
from gateway.app.api.routes import router
from gateway.app.api.tiktok_verify import router as tiktok_verify_router
from gateway.app.core.logging import configure_logging
from gateway.app.core.settings import get_settings
from gateway.app.db.session import Base, engine
from gateway.app.services.scheduler_service import start_scheduler, stop_scheduler

settings = get_settings()
configure_logging(settings.log_level)
_log = structlog.get_logger(__name__)

app = FastAPI(title="Marketing DEPA IA Gateway", version="0.1.0")
_cors_list = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Legales + verificación TikTok en la raíz del dominio ngrok (:8000), antes de /api.
app.include_router(legal_router)
app.include_router(tiktok_verify_router)
app.include_router(router)
app.include_router(auth_social_router)

if settings.prometheus_enabled:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app)
        _log.info("prometheus.enabled")
    except Exception as _prom_exc:  # noqa: BLE001
        _log.warning("prometheus.init_failed", error=str(_prom_exc))

_static_root = Path(__file__).resolve().parents[2] / "static"
_static_root.mkdir(parents=True, exist_ok=True)
(_static_root / "images").mkdir(parents=True, exist_ok=True)
(_static_root / "audio").mkdir(parents=True, exist_ok=True)
(_static_root / "videos").mkdir(parents=True, exist_ok=True)
(_static_root / "uploads").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_root)), name="static")


def _init_db() -> None:
    """Inicializa o valida la BD: SQLite crea tablas y aplica parches; Postgres solo comprueba conexión (esquema vía Alembic)."""
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
    """Al arrancar la app: BD y scheduler en segundo plano."""
    _init_db()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    """Al apagar: detiene el scheduler de campañas."""
    stop_scheduler()
