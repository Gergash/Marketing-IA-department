"""Endpoints REST bajo el prefijo `/api` (briefs, runs, campañas, salud)."""

import json

import kombu.exceptions
import redis
import redis.exceptions
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.auth import require_auth
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models import AgentRun, Brief, CampaignSchedule
from gateway.app.schemas.contracts import (
    ApproveRequest,
    BriefCreate,
    BriefResponse,
    CampaignFireResponse,
    CampaignScheduleCreate,
    CampaignScheduleResponse,
    ImageProvidersResponse,
    JobStatusResponse,
    RejectRequest,
    RunRequest,
    RunResponse,
    SocialPublishStatusResponse,
)
from gateway.app.services.pipeline_service import (
    approve_run,
    create_run,
    execute_pipeline,
    reject_run,
)
from gateway.app.services.scheduler_service import fire_campaign_by_id, sync_campaign_jobs
from workers.celery_app import celery_app
from workers.tasks import execute_pipeline_task

router = APIRouter(prefix="/api")


@router.get("/social/publish-status", response_model=SocialPublishStatusResponse)
def social_publish_status(
    tenant_id: str = Depends(require_auth),
) -> SocialPublishStatusResponse:
    """Indica qué integraciones de publicación están configuradas (sin exponer secretos)."""
    _ = tenant_id
    s = get_settings()
    return SocialPublishStatusResponse(
        social_provider=s.social_provider,
        linkedin_ready=bool(s.linkedin_access_token.strip()),
        uploadpost_ready=bool(s.uploadpost_api_key.strip()),
        meta_instagram_ready=bool(
            s.meta_page_access_token.strip() and s.instagram_business_account_id.strip()
        ),
    )


@router.get("/image/providers", response_model=ImageProvidersResponse)
def image_providers(
    tenant_id: str = Depends(require_auth),
) -> ImageProvidersResponse:
    """Lista generadores de imagen disponibles según `.env` (sin secretos)."""
    _ = tenant_id
    s = get_settings()
    providers: list[dict[str, str]] = []
    if s.stable_diffusion_url.strip():
        providers.append(
            {"id": "stable_diffusion", "label": "Stable Diffusion (local A1111/Forge)"}
        )
    if s.fal_api_key.strip():
        providers.append({"id": "fal", "label": "fal.ai (Flux Pro)"})
    return ImageProvidersResponse(
        default_provider=s.image_provider,
        providers=providers,
    )


@router.get("/health")
def health() -> dict:
    """Comprueba que el proceso de la API responde."""
    return {"status": "ok"}


@router.get("/health/background")
def background_health() -> dict:
    """Comprueba Redis (broker) y que al menos un worker Celery responda al ping."""
    s = get_settings()
    broker_ok = False
    worker_ok = False
    worker_nodes: list[str] = []

    try:
        client = redis.Redis.from_url(s.redis_url)
        broker_ok = bool(client.ping())
    except Exception:  # noqa: BLE001
        broker_ok = False

    try:
        pings = celery_app.control.ping(timeout=1.5)
        worker_ok = bool(pings)
        worker_nodes = [list(item.keys())[0] for item in pings if item]
    except Exception:  # noqa: BLE001
        worker_ok = False

    return {
        "status": "ok" if broker_ok and worker_ok else "degraded",
        "broker_ok": broker_ok,
        "worker_ok": worker_ok,
        "worker_nodes": worker_nodes,
    }


@router.post("/briefs", response_model=BriefResponse)
def create_brief(
    payload: BriefCreate,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> Brief:
    """Crea un brief de campaña asociado al tenant autenticado."""
    brief = Brief(tenant_id=tenant_id, **payload.model_dump())
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return brief


@router.get("/briefs", response_model=list[BriefResponse])
def list_briefs(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[Brief]:
    """Lista briefs del tenant, más recientes primero."""
    return list(
        db.execute(select(Brief).where(Brief.tenant_id == tenant_id).order_by(Brief.id.desc())).scalars().all()
    )


@router.post("/runs/sync", response_model=RunResponse)
def run_pipeline_sync(
    payload: RunRequest,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> RunResponse:
    """Ejecuta el pipeline de agentes de forma síncrona en el mismo proceso que la API."""
    run = create_run(
        db,
        brief_id=payload.brief_id,
        tenant_id=tenant_id,
        run_mode="sync",
        idempotency_key=payload.idempotency_key,
        content_format=payload.content_format,
    )
    try:
        result = execute_pipeline(
            db,
            run.id,
            publish=payload.publish,
            requires_approval=payload.requires_approval,
            idempotency_key=payload.idempotency_key,
            image_provider=payload.image_provider,
        )
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    db.refresh(run)
    return RunResponse(run_id=run.id, status=run.status, result=result)


@router.post("/runs/async", response_model=RunResponse)
def run_pipeline_async(
    payload: RunRequest,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> RunResponse:
    """Encola la ejecución del pipeline en Celery; responde con run en estado queued."""
    run = create_run(
        db,
        brief_id=payload.brief_id,
        tenant_id=tenant_id,
        run_mode="async",
        idempotency_key=payload.idempotency_key,
        content_format=payload.content_format,
    )
    try:
        execute_pipeline_task.apply_async(
            args=[
                run.id,
                payload.publish,
                payload.requires_approval,
                payload.idempotency_key,
                payload.image_provider,
            ],
        )
    except (
        redis.exceptions.ConnectionError,
        kombu.exceptions.OperationalError,
        OSError,
        RuntimeError,
    ) as exc:
        run.status = "failed"
        run.error_message = f"celery_broker_unavailable: {exc}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Redis no esta disponible en localhost:6379 (broker de Celery). "
                "Levanta Redis: docker compose -f infra/docker-compose.yml up -d redis. "
                "Luego inicia el worker: python -m celery -A workers.celery_app.celery_app worker -l info "
                "(desde la raiz del repo, con el venv activado). "
                "Si aparecio antes 'Celery application must be restarted', reinicia tambien uvicorn."
            ),
        ) from exc
    return RunResponse(run_id=run.id, status="queued")


@router.post("/runs/{run_id}/approve", response_model=RunResponse)
def approve_run_endpoint(
    run_id: int,
    payload: ApproveRequest = ApproveRequest(),
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> RunResponse:
    """Tras revisión humana: publica el contenido ya generado y marca el run como completado."""
    run = db.get(AgentRun, run_id)
    if not run or run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    try:
        result = approve_run(db, run_id, approved_by=payload.approved_by)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Error al publicar: {exc}",
        ) from exc
    return RunResponse(run_id=run_id, status="completed", result=result)


@router.post("/runs/{run_id}/reject", response_model=RunResponse)
def reject_run_endpoint(
    run_id: int,
    payload: RejectRequest = RejectRequest(),
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> RunResponse:
    """Rechaza un run pendiente de aprobación sin publicar."""
    run = db.get(AgentRun, run_id)
    if not run or run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    try:
        reject_run(db, run_id, reason=payload.reason, approved_by=payload.approved_by)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RunResponse(run_id=run_id, status="rejected")


@router.get("/runs/{run_id}", response_model=JobStatusResponse)
def get_run_status(
    run_id: int,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    """Devuelve estado, resultado JSON y metadatos de un run concreto."""
    run = db.get(AgentRun, run_id)
    if not run or run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    result = json.loads(run.result_json) if run.result_json else None
    return JobStatusResponse(
        run_id=run.id,
        status=run.status,
        result=result,
        error_message=run.error_message,
        approved_at=run.approved_at,
        approved_by=run.approved_by,
        content_format=getattr(run, "content_format", "feed") or "feed",
    )


@router.get("/runs", response_model=list[JobStatusResponse])
def list_runs(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[JobStatusResponse]:
    """Lista todas las ejecuciones del tenant."""
    runs = db.execute(
        select(AgentRun).where(AgentRun.tenant_id == tenant_id).order_by(AgentRun.id.desc())
    ).scalars().all()
    return [
        JobStatusResponse(
            run_id=run.id,
            status=run.status,
            result=json.loads(run.result_json) if run.result_json else None,
            error_message=run.error_message,
            approved_at=run.approved_at,
            approved_by=run.approved_by,
            content_format=getattr(run, "content_format", "feed") or "feed",
        )
        for run in runs
    ]


@router.post("/campaigns", response_model=CampaignScheduleResponse)
def create_campaign(
    payload: CampaignScheduleCreate,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> CampaignSchedule:
    """Crea campaña programada (cron). El scheduler la registra al instante (sin esperar el heartbeat de 5 min)."""
    item = CampaignSchedule(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    sync_campaign_jobs()
    return item


@router.get("/campaigns", response_model=list[CampaignScheduleResponse])
def list_campaigns(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[CampaignSchedule]:
    """Lista campañas programadas del tenant."""
    return list(
        db.execute(select(CampaignSchedule).where(CampaignSchedule.tenant_id == tenant_id)).scalars().all()
    )


@router.post("/campaigns/{campaign_id}/fire", response_model=CampaignFireResponse)
def fire_campaign(
    campaign_id: int,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> CampaignFireResponse:
    """Dispara una campaña de inmediato (prueba de fuego). Genera contenido en pending_approval sin publicar."""
    campaign = db.get(CampaignSchedule, campaign_id)
    if not campaign or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaña no encontrada")
    if not campaign.enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Campaña desactivada")

    run_id = fire_campaign_by_id(campaign_id)
    if run_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo ejecutar la campaña; revisa logs del gateway",
        )

    run = db.get(AgentRun, run_id)
    return CampaignFireResponse(
        campaign_id=campaign_id,
        run_id=run_id,
        status=run.status if run else "unknown",
    )
