import sys

from celery import Celery

from gateway.app.core.settings import get_settings

settings = get_settings()

# Solo broker Redis: el estado del run se persiste en BD desde el worker.
# Evita que el proceso de FastAPI abra el consumidor de resultados al hacer .delay().
celery_app = Celery("marketing_workers", broker=settings.redis_url)
celery_app.conf.update(
    result_backend=None,
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_time_limit=120,
    task_soft_time_limit=90,
)

# Windows: prefork (billiard) suele fallar con PermissionError en semaforos (WinError 5).
# "threads" usa ThreadPoolExecutor (sin SpawnPoolWorker / sin multiprocessing entre tareas).
# "solo" tambien evita prefork, pero en algunos entornos el CLI sigue eligiendo prefork; threads es mas robusto.
if sys.platform == "win32":
    celery_app.conf.worker_pool = "threads"
    celery_app.conf.worker_concurrency = 4
