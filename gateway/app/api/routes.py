import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.db.session import get_db
from gateway.app.models import AgentRun, Brief, CampaignSchedule
from gateway.app.schemas.contracts import (
    BriefCreate,
    BriefResponse,
    CampaignScheduleCreate,
    CampaignScheduleResponse,
    JobStatusResponse,
    RunRequest,
    RunResponse,
)
from gateway.app.services.pipeline_service import create_run, execute_pipeline
from gateway.app.core.security import require_role
from workers.tasks import execute_pipeline_task

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/briefs", response_model=BriefResponse)
def create_brief(
    payload: BriefCreate,
    user=Depends(require_role("editor")),
    db: Session = Depends(get_db),
) -> Brief:
    tenant_id, _ = user
    brief = Brief(tenant_id=tenant_id, **payload.model_dump())
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return brief


@router.get("/briefs", response_model=list[BriefResponse])
def list_briefs(
    user=Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> list[Brief]:
    tenant_id, _ = user
    return list(
        db.execute(select(Brief).where(Brief.tenant_id == tenant_id).order_by(Brief.id.desc())).scalars().all()
    )


@router.post("/runs/sync", response_model=RunResponse)
def run_pipeline_sync(
    payload: RunRequest,
    user=Depends(require_role("editor")),
    db: Session = Depends(get_db),
) -> RunResponse:
    tenant_id, _ = user
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

    return RunResponse(run_id=run.id, status="completed", result=result)


@router.post("/runs/async", response_model=RunResponse)
def run_pipeline_async(
    payload: RunRequest,
    user=Depends(require_role("editor")),
    db: Session = Depends(get_db),
) -> RunResponse:
    tenant_id, _ = user
    run = create_run(
        db,
        brief_id=payload.brief_id,
        tenant_id=tenant_id,
        run_mode="async",
        idempotency_key=payload.idempotency_key,
    )
    execute_pipeline_task.delay(
        run.id,
        payload.publish,
        payload.requires_approval,
        payload.idempotency_key,
    )
    return RunResponse(run_id=run.id, status="queued")


@router.get("/runs/{run_id}", response_model=JobStatusResponse)
def get_run_status(
    run_id: int,
    user=Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    tenant_id, _ = user
    run = db.get(AgentRun, run_id)
    if not run or run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    result = json.loads(run.result_json) if run.result_json else None
    return JobStatusResponse(run_id=run.id, status=run.status, result=result, error_message=run.error_message)


@router.get("/runs", response_model=list[JobStatusResponse])
def list_runs(
    user=Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> list[JobStatusResponse]:
    tenant_id, _ = user
    runs = db.execute(select(AgentRun).where(AgentRun.tenant_id == tenant_id).order_by(AgentRun.id.desc())).scalars().all()
    return [
        JobStatusResponse(
            run_id=run.id,
            status=run.status,
            result=json.loads(run.result_json) if run.result_json else None,
            error_message=run.error_message,
        )
        for run in runs
    ]


@router.post("/campaigns", response_model=CampaignScheduleResponse)
def create_campaign(
    payload: CampaignScheduleCreate,
    user=Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> CampaignSchedule:
    tenant_id, _ = user
    item = CampaignSchedule(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/campaigns", response_model=list[CampaignScheduleResponse])
def list_campaigns(
    user=Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> list[CampaignSchedule]:
    tenant_id, _ = user
    return list(db.execute(select(CampaignSchedule).where(CampaignSchedule.tenant_id == tenant_id)).scalars().all())
