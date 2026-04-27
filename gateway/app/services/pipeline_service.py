from __future__ import annotations

import json
from datetime import datetime

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.marketing_agents import BriefInput, MarketingPipeline
from agents.marketing_agents.schemas import CopyOutput, DesignOutput
from gateway.app.core.settings import get_settings
from gateway.app.models import AgentRun, Brief, GeneratedAsset, Publication

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internos
# ---------------------------------------------------------------------------

def _brief_input(brief: Brief) -> BriefInput:
    return BriefInput(
        tema=brief.tema,
        publico_objetivo=brief.publico_objetivo,
        red_social=brief.red_social,
        objetivo=brief.objetivo,
        tono_marca=brief.tono_marca,
        idioma=brief.idioma,
    )


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


def _notify_slack(webhook_url: str, run_id: int, brief_tema: str) -> None:
    if not webhook_url:
        return
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Marketing DEPA IA — Aprobación requerida"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Run #{run_id}* está listo para revisión.\n"
                        f"*Tema:* `{brief_tema}`\n\n"
                        f"Aprueba en el dashboard o vía API:\n"
                        f"`POST /api/runs/{run_id}/approve`\n"
                        f"`POST /api/runs/{run_id}/reject`"
                    ),
                },
            },
        ]
    }
    try:
        with httpx.Client(timeout=5) as client:
            client.post(webhook_url, json=payload)
        logger.info("slack.notified", run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("slack.notify_error", error=str(exc))


def _publish_via_go(result: dict, brief: Brief, idempotency_key: str | None, run: AgentRun) -> None:
    """Intenta publicar mediante el microservicio Go. Actualiza result in-place."""
    settings = get_settings()
    try:
        payload = {
            "platform": brief.red_social,
            "copy": result["copy"]["copy_final"],
            "image_url": result["design"]["image_url"],
            "idempotency_key": idempotency_key,
        }
        with httpx.Client(timeout=15) as client:
            published = client.post(f"{settings.go_publisher_url}/publish", json=payload)
        if published.is_success:
            result["publish_result"] = published.json()
    except Exception as exc:  # noqa: BLE001
        run.error_message = f"go_publisher_error: {exc}"
        logger.warning("go_publisher.error", error=str(exc))


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

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

    # Idempotencia: si ya existe un run completado con la misma key, reutilizarlo.
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
    brief_in = _brief_input(brief)

    if requires_approval:
        # Human-in-the-loop: generar estrategia + copy + diseño + QA,
        # pero NO publicar. Esperar aprobación humana.
        result = pipeline.run(brief_in, publish=False, idempotency_key=idempotency_key)
        run.result_json = json.dumps(result, ensure_ascii=True)
        run.status = "pending_approval"
        db.add(run)
        db.commit()
        _notify_slack(get_settings().slack_webhook_url, run.id, brief.tema)
        logger.info("pipeline.pending_approval", run_id=run.id)
        return result

    # Sin aprobación requerida: ejecutar y publicar directamente.
    result = pipeline.run(brief_in, publish=publish, idempotency_key=idempotency_key)

    if publish and result.get("quality", {}).get("approved", False):
        _publish_via_go(result, brief, idempotency_key, run)

    _persist_result(db, run, result, brief.red_social)
    db.commit()
    db.refresh(run)
    return result


def approve_run(db: Session, run_id: int, *, approved_by: str = "human") -> dict:
    """Aprueba un run en estado pending_approval y ejecuta la publicación."""
    run = db.get(AgentRun, run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")
    if run.status != "pending_approval":
        raise ValueError(f"Run {run_id} no está en estado pending_approval (actual: {run.status})")
    if not run.result_json:
        raise ValueError(f"Run {run_id} no tiene resultado previo para publicar")

    brief = db.get(Brief, run.brief_id)
    if not brief:
        raise ValueError(f"Brief {run.brief_id} not found")

    result = json.loads(run.result_json)

    if not result.get("quality", {}).get("approved", False):
        raise ValueError("QA rechazó el contenido; no se puede publicar")

    # Publicar usando los datos ya generados (no se vuelven a gastar créditos de LLM/imagen).
    copy = CopyOutput(**result["copy"])
    design = DesignOutput(**result["design"])

    pipeline = MarketingPipeline()
    publish_result = pipeline.publisher.run(
        brief.red_social, copy, design, idempotency_key=run.idempotency_key
    )
    result["publish_result"] = publish_result.model_dump()

    run.approved_at = datetime.utcnow()
    run.approved_by = approved_by
    _persist_result(db, run, result, brief.red_social)
    db.commit()
    db.refresh(run)
    logger.info("pipeline.approved_and_published", run_id=run_id, approved_by=approved_by)
    return result


def reject_run(db: Session, run_id: int, *, reason: str = "", approved_by: str = "human") -> None:
    """Rechaza un run en estado pending_approval."""
    run = db.get(AgentRun, run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")
    if run.status != "pending_approval":
        raise ValueError(f"Run {run_id} no está en estado pending_approval (actual: {run.status})")

    run.status = "rejected"
    run.approved_at = datetime.utcnow()
    run.approved_by = approved_by
    if reason:
        run.error_message = f"rejected: {reason}"
    db.add(run)
    db.commit()
    logger.info("pipeline.rejected", run_id=run_id, reason=reason)
