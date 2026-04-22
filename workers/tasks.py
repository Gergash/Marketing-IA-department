import structlog
from celery import Task

from gateway.app.db.session import SessionLocal
from gateway.app.services.pipeline_service import execute_pipeline
from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


class BaseTaskWithRetry(Task):
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_kwargs = {"max_retries": 3}


@celery_app.task(bind=True, base=BaseTaskWithRetry)
def execute_pipeline_task(
    self,  # noqa: ANN001
    run_id: int,
    publish: bool,
    requires_approval: bool,
    idempotency_key: str | None,
) -> dict:
    with SessionLocal() as db:
        logger.info("execute_pipeline_task.start", run_id=run_id)
        result = execute_pipeline(
            db,
            run_id,
            publish=publish,
            requires_approval=requires_approval,
            idempotency_key=idempotency_key,
        )
        logger.info("execute_pipeline_task.done", run_id=run_id)
        return result
