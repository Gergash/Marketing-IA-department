from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from gateway.app.db.session import SessionLocal
from gateway.app.models import CampaignSchedule


scheduler = BackgroundScheduler(timezone="UTC")


def _heartbeat_job() -> None:
    # Placeholder to keep scheduler active; campaign trigger can be added per record.
    with SessionLocal() as db:
        db.execute(select(CampaignSchedule).where(CampaignSchedule.enabled == True)).all()  # noqa: E712


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(_heartbeat_job, "interval", minutes=5, id="campaign-heartbeat", replace_existing=True)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
