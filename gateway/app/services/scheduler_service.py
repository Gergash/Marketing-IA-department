"""Scheduler en proceso (APScheduler) para tareas periódicas relacionadas con campañas."""

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from gateway.app.db.session import SessionLocal
from gateway.app.models import CampaignSchedule


scheduler = BackgroundScheduler(timezone="UTC")


def _heartbeat_job() -> None:
    """Job periódico placeholder: mantiene el scheduler activo; futuro disparo de campañas por cron."""
    # Placeholder to keep scheduler active; campaign trigger can be added per record.
    with SessionLocal() as db:
        db.execute(select(CampaignSchedule).where(CampaignSchedule.enabled == True)).all()  # noqa: E712


def start_scheduler() -> None:
    """Registra el heartbeat cada 5 minutos e inicia APScheduler si no estaba en marcha."""
    if scheduler.running:
        return
    scheduler.add_job(_heartbeat_job, "interval", minutes=5, id="campaign-heartbeat", replace_existing=True)
    scheduler.start()


def stop_scheduler() -> None:
    """Apaga el scheduler sin bloquear indefinidamente."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
