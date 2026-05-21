"""Scheduler en proceso (APScheduler): sincroniza y dispara campañas programadas por cron."""

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from gateway.app.db.session import SessionLocal
from gateway.app.models import Brief, CampaignSchedule

logger = structlog.get_logger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def _fire_campaign(
    campaign_id: int,
    tenant_id: str,
    tema: str,
    red_social: str,
    objetivo: str,
) -> None:
    """Crea un brief y ejecuta el pipeline completo para una campaña programada."""
    # Importación diferida para evitar circularidad en startup
    from gateway.app.services.pipeline_service import create_run, execute_pipeline

    with SessionLocal() as db:
        campaign = db.get(CampaignSchedule, campaign_id)
        if not campaign or not campaign.enabled:
            logger.info("scheduler.campaign_skipped", campaign_id=campaign_id, reason="disabled_or_deleted")
            return

        brief = Brief(
            tenant_id=tenant_id,
            tema=tema,
            publico_objetivo="audiencia objetivo de la marca",
            red_social=red_social,
            objetivo=objetivo,
        )
        db.add(brief)
        db.commit()
        db.refresh(brief)

        idem_key = f"campaign-{campaign_id}-{brief.id}"
        run = create_run(
            db,
            brief_id=brief.id,
            tenant_id=tenant_id,
            run_mode="scheduled",
            idempotency_key=idem_key,
        )
        try:
            execute_pipeline(
                db,
                run.id,
                publish=True,
                requires_approval=True,
                idempotency_key=idem_key,
            )
            logger.info("scheduler.campaign_fired", campaign_id=campaign_id, run_id=run.id)
        except Exception as exc:  # noqa: BLE001
            logger.error("scheduler.campaign_error", campaign_id=campaign_id, error=str(exc))


def _sync_campaign_jobs() -> None:
    """Sincroniza jobs del scheduler con campañas activas en BD; elimina los de campañas desactivadas."""
    with SessionLocal() as db:
        rows = db.execute(
            select(CampaignSchedule).where(CampaignSchedule.enabled == True)  # noqa: E712
        ).scalars().all()
        # Extraemos datos antes de cerrar la sesión
        campaigns = [
            {
                "id": c.id,
                "tenant_id": c.tenant_id,
                "tema": c.tema,
                "red_social": c.red_social,
                "objetivo": c.objetivo,
                "cron_expr": c.cron_expr,
            }
            for c in rows
        ]

    active_ids = {c["id"] for c in campaigns}

    # Eliminar jobs de campañas desactivadas o borradas
    for job in scheduler.get_jobs():
        if not job.id.startswith("campaign-") or job.id == "campaign-heartbeat":
            continue
        try:
            job_campaign_id = int(job.id.split("-")[1])
        except (IndexError, ValueError):
            continue
        if job_campaign_id not in active_ids:
            scheduler.remove_job(job.id)
            logger.info("scheduler.job_removed", campaign_id=job_campaign_id)

    # Agregar o actualizar jobs de campañas activas
    for campaign in campaigns:
        job_id = f"campaign-{campaign['id']}"
        try:
            trigger = CronTrigger.from_crontab(campaign["cron_expr"], timezone="UTC")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "scheduler.invalid_cron",
                campaign_id=campaign["id"],
                cron=campaign["cron_expr"],
                error=str(exc),
            )
            continue

        if scheduler.get_job(job_id):
            scheduler.reschedule_job(job_id, trigger=trigger)
        else:
            scheduler.add_job(
                _fire_campaign,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                kwargs={
                    "campaign_id": campaign["id"],
                    "tenant_id": campaign["tenant_id"],
                    "tema": campaign["tema"],
                    "red_social": campaign["red_social"],
                    "objetivo": campaign["objetivo"],
                },
            )
            logger.info("scheduler.job_added", campaign_id=campaign["id"], cron=campaign["cron_expr"])


def start_scheduler() -> None:
    """Inicia APScheduler, registra el heartbeat de sincronización y carga campañas existentes."""
    if scheduler.running:
        return
    scheduler.add_job(
        _sync_campaign_jobs,
        "interval",
        minutes=5,
        id="campaign-heartbeat",
        replace_existing=True,
    )
    scheduler.start()
    _sync_campaign_jobs()


def stop_scheduler() -> None:
    """Apaga el scheduler sin bloquear indefinidamente."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
