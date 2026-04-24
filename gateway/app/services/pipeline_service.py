import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.marketing_agents import BriefInput, MarketingPipeline
from gateway.app.core.settings import get_settings
from gateway.app.models import AgentRun, Brief, GeneratedAsset, Publication


def _persist_result(db: Session, run: AgentRun, result: dict, platform: str) -> None:
    run.result_json = json.dumps(result, ensure_ascii=True)
    run.status = "completed"
    db.add(run)

    design = result.get("design") or {}
    db.add(
        GeneratedAsset(
            tenant_id=run.tenant_id,
            run_id=run.id,
            image_url=design.get("image_url", ""),
            image_prompt=design.get("image_prompt", ""),
        )
    )

    publish_result = result.get("publish_result")
    if publish_result:
        db.add(
            Publication(
                tenant_id=run.tenant_id,
                run_id=run.id,
                platform=platform,
                publication_url=publish_result.get("publication_url", ""),
                platform_post_id=publish_result.get("platform_post_id", ""),
                approved=result.get("quality", {}).get("approved", False),
            )
        )


def create_run(
    db: Session,
    *,
    brief_id: int,
    tenant_id: str,
    run_mode: str,
    idempotency_key: str | None,
) -> AgentRun:
    run = AgentRun(
        tenant_id=tenant_id,
        brief_id=brief_id,
        run_mode=run_mode,
        status="queued",
        idempotency_key=idempotency_key,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_pipeline(
    db: Session,
    run_id: int,
    *,
    publish: bool,
    requires_approval: bool,
    idempotency_key: str | None,
) -> dict:
    run = db.get(AgentRun, run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")

    if idempotency_key:
        existent = db.execute(
            select(AgentRun).where(
                AgentRun.idempotency_key == idempotency_key,
                AgentRun.status == "completed",
                AgentRun.id != run.id,
            )
        ).scalar_one_or_none()
        if existent and existent.result_json:
            run.status = "deduplicated"
            run.result_json = existent.result_json
            db.commit()
            return json.loads(existent.result_json)

    brief = db.get(Brief, run.brief_id)
    if not brief:
        raise ValueError(f"Brief {run.brief_id} not found")

    run.status = "running"
    db.commit()

    pipeline = MarketingPipeline()
    brief_in = BriefInput(
        tema=brief.tema,
        publico_objetivo=brief.publico_objetivo,
        red_social=brief.red_social,
        objetivo=brief.objetivo,
        tono_marca=brief.tono_marca,
        idioma=brief.idioma,
    )
    result = pipeline.run(
        brief_in,
        publish=publish and not requires_approval,
        idempotency_key=idempotency_key,
    )

    # If publish is requested and approval is disabled, delegate publication to Go service.
    if publish and not requires_approval and result.get("quality", {}).get("approved", False):
        settings = get_settings()
        with httpx.Client(timeout=15) as client:
            try:
                payload = {
                    "platform": brief.red_social,
                    "copy": result["copy"]["copy_final"],
                    "image_url": result["design"]["image_url"],
                    "idempotency_key": idempotency_key,
                }
                published = client.post(f"{settings.go_publisher_url}/publish", json=payload)
                if published.is_success:
                    result["publish_result"] = published.json()
            except Exception as exc:  # noqa: BLE001
                run.error_message = f"go_publisher_error: {exc}"

    _persist_result(db, run, result, brief.red_social)
    db.commit()
    db.refresh(run)
    return result
