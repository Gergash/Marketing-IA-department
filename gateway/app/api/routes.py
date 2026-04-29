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
    CampaignScheduleCreate,
    CampaignScheduleResponse,
    JobStatusResponse,
    RejectRequest,
    RunRequest,
    RunResponse,
)
from gateway.app.services.pipeline_service import (
    approve_run,
    create_run,
    execute_pipeline,
    reject_run,
)
from workers.celery_app import celery_app
from workers.tasks import execute_pipeline_task

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/health/background")
def background_health() -> dict:
    """Broker/worker health for background processing."""
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
    return list(
        db.execute(select(Brief).where(Brief.tenant_id == tenant_id).order_by(Brief.id.desc())).scalars().all()
    )


@router.post("/runs/sync", response_model=RunResponse)
def run_pipeline_sync(
    payload: RunRequest,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> RunResponse:
    run = create_run(
        db,
        brief_id=payload.brief_id,
        tenant_id=tenant_id,
        run_mode="sync",
        idempotency_key=payload.idempotency_key,
    )
    try:
        result = execute_pipeline(
            db,
            run.id,
            publish=payload.publish,
            requires_approval=payload.requires_approval,
            idempotency_key=payload.idempotency_key,
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
    run = create_run(
        db,
        brief_id=payload.brief_id,
        tenant_id=tenant_id,
        run_mode="async",
        idempotency_key=payload.idempotency_key,
    )
    try:
        execute_pipeline_task.apply_async(
            args=[
                run.id,
                payload.publish,
                payload.requires_approval,
                payload.idempotency_key,
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
    run = db.get(AgentRun, run_id)
    if not run or run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    try:
        result = approve_run(db, run_id, approved_by=payload.approved_by)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RunResponse(run_id=run_id, status="completed", result=result)


@router.post("/runs/{run_id}/reject", response_model=RunResponse)
def reject_run_endpoint(
    run_id: int,
    payload: RejectRequest = RejectRequest(),
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> RunResponse:
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
    )


@router.get("/runs", response_model=list[JobStatusResponse])
def list_runs(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[JobStatusResponse]:
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
        )
        for run in runs
    ]


@router.post("/campaigns", response_model=CampaignScheduleResponse)
def create_campaign(
    payload: CampaignScheduleCreate,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> CampaignSchedule:
    item = CampaignSchedule(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/campaigns", response_model=list[CampaignScheduleResponse])
def list_campaigns(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[CampaignSchedule]:
    return list(
        db.execute(select(CampaignSchedule).where(CampaignSchedule.tenant_id == tenant_id)).scalars().all()
    )
