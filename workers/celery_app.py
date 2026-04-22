from celery import Celery

from gateway.app.core.settings import get_settings

settings = get_settings()

celery_app = Celery("marketing_workers", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_time_limit=120,
    task_soft_time_limit=90,
)
