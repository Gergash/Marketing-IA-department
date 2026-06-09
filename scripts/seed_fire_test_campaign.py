"""Inserta o actualiza la campaña de la Prueba de Fuego del Scheduler.

Uso (desde la raíz del repo, venv activado):
    python scripts/seed_fire_test_campaign.py
    python scripts/seed_fire_test_campaign.py --fire-now
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar como: python scripts/seed_fire_test_campaign.py
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from gateway.app.core.settings import get_settings
from gateway.app.db.session import Base, SessionLocal, engine
from gateway.app.db.schema_patches import apply_lightweight_migrations
from gateway.app.models import CampaignSchedule
from gateway.app.services.scheduler_service import fire_campaign_by_id, sync_campaign_jobs

FIRE_TEST_TEMA = "Prueba de Fuego Scheduler"
FIRE_TEST_CRON = "* * * * *"  # cada minuto (UTC); para demo manual usa --fire-now


def _ensure_schema() -> None:
    dialect = engine.dialect.name
    if dialect == "sqlite":
        Base.metadata.create_all(bind=engine)
        apply_lightweight_migrations(engine)
    else:
        # PostgreSQL: esquema vía Alembic (alembic upgrade head)
        with engine.connect():
            pass


def seed_fire_test_campaign(*, fire_now: bool = False) -> int:
    """Crea/actualiza la campaña de prueba y sincroniza APScheduler. Retorna campaign_id."""
    settings = get_settings()
    _ensure_schema()

    with SessionLocal() as db:
        existing = db.execute(
            select(CampaignSchedule).where(
                CampaignSchedule.tenant_id == settings.default_tenant_id,
                CampaignSchedule.tema == FIRE_TEST_TEMA,
            )
        ).scalar_one_or_none()

        if existing:
            existing.cron_expr = FIRE_TEST_CRON
            existing.red_social = "instagram"
            existing.objetivo = "branding"
            existing.enabled = True
            db.commit()
            db.refresh(existing)
            campaign = existing
            print(f"Campaña existente actualizada (id={campaign.id})")
        else:
            campaign = CampaignSchedule(
                tenant_id=settings.default_tenant_id,
                tema=FIRE_TEST_TEMA,
                red_social="instagram",
                objetivo="branding",
                cron_expr=FIRE_TEST_CRON,
                enabled=True,
            )
            db.add(campaign)
            db.commit()
            db.refresh(campaign)
            print(f"Campaña creada (id={campaign.id})")

    # Solo sincroniza jobs si el scheduler ya está activo (proceso uvicorn).
    from gateway.app.services.scheduler_service import scheduler

    if scheduler.running:
        sync_campaign_jobs()
        print(f"Scheduler sincronizado. Cron: {FIRE_TEST_CRON} (UTC, cada minuto)")
    else:
        print(
            "Campaña guardada en BD. Inicia uvicorn para registrar el job en APScheduler "
            "(o usa POST /api/campaigns que sincroniza al crear)."
        )
    print("El scheduler vive en el proceso API (uvicorn), no en este script.")

    if fire_now:
        run_id = fire_campaign_by_id(campaign.id)
        if run_id:
            print(f"Disparo manual OK → run_id={run_id} (debe quedar en pending_approval)")
        else:
            print("Disparo manual falló; revisa logs del gateway", file=sys.stderr)
            sys.exit(1)

    return campaign.id


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed de la Prueba de Fuego del Scheduler")
    parser.add_argument(
        "--fire-now",
        action="store_true",
        help="Dispara la campaña de inmediato (sin esperar al cron)",
    )
    args = parser.parse_args()
    seed_fire_test_campaign(fire_now=args.fire_now)


if __name__ == "__main__":
    main()
