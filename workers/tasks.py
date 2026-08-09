"""Tareas Celery ejecutadas por workers (pipeline asíncrono y healthcheck)."""

import structlog
from celery import Task

from agents.marketing_agents.thought_stream import RunCancelledByUser
from gateway.app.db.session import SessionLocal
from gateway.app.services.pipeline_service import execute_pipeline
from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


class BaseTaskWithRetry(Task):
    """Tarea Celery base con reintentos exponenciales ante cualquier excepción (hasta 3 veces)."""

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
    image_provider: str | None = None,
    archetype_override: str | None = None,
    user_asset_url: str | None = None,
    alter_image_with_ai: bool = False,
    visual_instructions: str | None = None,
    drive_folder_id: str | None = None,
    revision_notes: str | None = None,
) -> dict:
    """Tarea asíncrona: abre sesión BD y ejecuta `execute_pipeline` con los mismos flags que en la API."""
    with SessionLocal() as db:
        logger.info("execute_pipeline_task.start", run_id=run_id)
        try:
            result = execute_pipeline(
                db,
                run_id,
                publish=publish,
                requires_approval=requires_approval,
                idempotency_key=idempotency_key,
                image_provider=image_provider,
                archetype_override=archetype_override,
                user_asset_url=user_asset_url,
                alter_image_with_ai=alter_image_with_ai,
                visual_instructions=visual_instructions,
                drive_folder_id=drive_folder_id,
                revision_notes=revision_notes,
            )
        except RunCancelledByUser as exc:
            # `autoretry_for=(Exception,)` reintentaria un run que el usuario detuvo a proposito.
            logger.info("execute_pipeline_task.cancelled", run_id=run_id, checkpoint=exc.checkpoint)
            return {"status": "rejected", "checkpoint": exc.checkpoint}
        logger.info("execute_pipeline_task.done", run_id=run_id)
        return result


@celery_app.task(bind=True, base=Task, queue="video_render")
def execute_video_pipeline_task(
    self,  # noqa: ANN001
    run_id: int,
    publish: bool,
    requires_approval: bool,
    idempotency_key: str | None,
    image_provider: str | None = None,
    archetype_override: str | None = None,
    user_asset_url: str | None = None,
    alter_image_with_ai: bool = False,
    visual_instructions: str | None = None,
    drive_folder_id: str | None = None,
    revision_notes: str | None = None,
) -> dict:
    """Tarea de reels en cola dedicada `video_render`: Task base plano (SIN autoretry_for).

    Un render de video tarda minutos y cuesta dinero real (Shotstack/ElevenLabs); reintentar
    automaticamente re-renderizaria y duplicaria costo/medios, por eso NO hereda de
    `BaseTaskWithRetry` (que trae `autoretry_for=(Exception,)` incluso con max_retries=0).
    """
    with SessionLocal() as db:
        logger.info("execute_video_pipeline_task.start", run_id=run_id)
        try:
            result = execute_pipeline(
                db,
                run_id,
                publish=publish,
                requires_approval=requires_approval,
                idempotency_key=idempotency_key,
                image_provider=image_provider,
                archetype_override=archetype_override,
                user_asset_url=user_asset_url,
                alter_image_with_ai=alter_image_with_ai,
                visual_instructions=visual_instructions,
                drive_folder_id=drive_folder_id,
                revision_notes=revision_notes,
            )
        except RunCancelledByUser as exc:
            logger.info("execute_video_pipeline_task.cancelled", run_id=run_id, checkpoint=exc.checkpoint)
            return {"status": "rejected", "checkpoint": exc.checkpoint}
        logger.info("execute_video_pipeline_task.done", run_id=run_id)
        return result


@celery_app.task(name="workers.healthcheck_task")
def healthcheck_task() -> dict:
    """Tarea mínima para comprobar que el worker puede consumir y ejecutar jobs."""
    return {"status": "ok"}
