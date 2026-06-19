"""Servicio de dominio: creación de runs, ejecución del pipeline de agentes, aprobación y persistencia."""

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
from gateway.app.models import AgentRun, Brief, GeneratedAsset, OAuthToken, Publication

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internos
# ---------------------------------------------------------------------------

def _brief_input(brief: Brief) -> BriefInput:
    """Convierte la entidad ORM `Brief` al DTO `BriefInput` del pipeline de agentes."""
    return BriefInput(
        tema=brief.tema,
        publico_objetivo=brief.publico_objetivo,
        red_social=brief.red_social,
        objetivo=brief.objetivo,
        tono_marca=brief.tono_marca,
        idioma=brief.idioma,
    )


def _persist_result(db: Session, run: AgentRun, result: dict, platform: str) -> None:
    """Guarda JSON del resultado, marca run completado y persiste asset gráfico y publicación si aplica."""
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
    """Envía un mensaje a Slack cuando un run queda pendiente de aprobación humana."""
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


_OAUTH_PROVIDER_MAP = {
    "instagram": "meta",
    "ig": "meta",
    "facebook": "meta",
    "linkedin": "linkedin",
}


def _publish_via_go(
    result: dict,
    brief: Brief,
    idempotency_key: str | None,
    run: AgentRun,
    db: Session,
) -> str:
    """POST al sidecar Go `/publish`. Retorna: success | failed | unavailable."""
    settings = get_settings()
    platform = brief.red_social.lower()
    oauth_provider = _OAUTH_PROVIDER_MAP.get(platform)

    access_token = ""
    account_id = ""

    if oauth_provider:
        token_row = db.execute(
            select(OAuthToken).where(
                OAuthToken.tenant_id == run.tenant_id,
                OAuthToken.provider == oauth_provider,
            )
        ).scalar_one_or_none()
        if token_row:
            access_token = token_row.access_token
            account_id = token_row.account_id

    if not access_token:
        return "unavailable"

    # Sustituye localhost por la URL pública (Meta exige HTTPS accesible externamente)
    image_url = result["design"]["image_url"]
    public_base = settings.public_image_base_url.rstrip("/")
    if image_url.startswith("http://localhost:8000"):
        image_url = image_url.replace("http://localhost:8000", public_base, 1)

    try:
        payload = {
            "platform": brief.red_social,
            "copy": result["copy"]["copy_final"],
            "image_url": image_url,
            "idempotency_key": idempotency_key or "",
            "content_format": getattr(run, "content_format", None) or "feed",
            "access_token": access_token,
            "account_id": account_id,
        }
        with httpx.Client(timeout=60) as client:
            published = client.post(f"{settings.go_publisher_url}/publish", json=payload)
        if published.is_success:
            result["publish_result"] = published.json()
            logger.info("go_publisher.ok", platform=brief.red_social)
            return "success"
        logger.warning("go_publisher.non_2xx", status=published.status_code, body=published.text[:200])
        run.error_message = f"go_publisher_http_{published.status_code}"
        return "failed"
    except Exception as exc:  # noqa: BLE001
        run.error_message = f"go_publisher_error: {exc}"
        logger.warning("go_publisher.error", error=str(exc))
        return "unavailable"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def _normalize_content_format(value: str | None) -> str:
    """Normaliza el formato de publicación a `feed` o `story` (valores desconocidos → feed)."""
    v = (value or "feed").lower()
    return v if v in ("feed", "story") else "feed"


def create_run(
    db: Session,
    *,
    brief_id: int,
    tenant_id: str,
    run_mode: str,
    idempotency_key: str | None,
    content_format: str = "feed",
) -> AgentRun:
    """Inserta un `AgentRun` en cola con modo sync/async, clave de idempotencia y formato feed/story."""
    run = AgentRun(
        tenant_id=tenant_id,
        brief_id=brief_id,
        run_mode=run_mode,
        status="queued",
        idempotency_key=idempotency_key,
        content_format=_normalize_content_format(content_format),
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
    image_provider: str | None = None,
) -> dict:
    """Orquesta el pipeline completo: deduplicación, agentes, aprobación humana opcional, persistencia y publicación."""
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
    content_format = _normalize_content_format(getattr(run, "content_format", None))

    if requires_approval:
        # Human-in-the-loop: generar estrategia + copy + diseño + QA,
        # pero NO publicar. Esperar aprobación humana.
        result = pipeline.run(
            brief_in,
            publish=False,
            idempotency_key=idempotency_key,
            content_format=content_format,
            image_provider=image_provider,
        )
        run.result_json = json.dumps(result, ensure_ascii=True)
        run.status = "pending_approval"
        db.add(run)
        db.commit()
        _notify_slack(get_settings().slack_webhook_url, run.id, brief.tema)
        logger.info("pipeline.pending_approval", run_id=run.id)
        return result

    # Sin aprobación requerida: ejecutar y publicar directamente.
    result = pipeline.run(
        brief_in,
        publish=publish,
        idempotency_key=idempotency_key,
        content_format=content_format,
        image_provider=image_provider,
    )

    if publish and result.get("quality", {}).get("approved", False):
        _publish_via_go(result, brief, idempotency_key, run, db)

    _persist_result(db, run, result, brief.red_social)
    db.commit()
    db.refresh(run)
    return result


def approve_run(db: Session, run_id: int, *, approved_by: str = "human") -> dict:
    """Aprueba un run en `pending_approval`, publica con el mismo `content_format` guardado y persiste resultado."""
    run = db.get(AgentRun, run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")
    if run.status == "completed":
        if run.result_json:
            return json.loads(run.result_json)
        raise ValueError(f"Run {run_id} ya está completado")
    if run.status == "publishing":
        raise ValueError(f"Run {run_id} ya se está publicando; espera unos segundos")
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

    # Bloqueo optimista: evita doble clic / requests concurrentes que dupliquen posts.
    run.status = "publishing"
    db.commit()

    try:
        go_outcome = _publish_via_go(result, brief, run.idempotency_key, run, db)

        # Solo fallback Python si Go no respondió (caído). Si Go falló en Meta, NO reintentar
        # en Python — eso creaba contenedores duplicados y posts repetidos en Instagram.
        if go_outcome == "unavailable" and not result.get("publish_result"):
            logger.warning("approve_run.go_fallback", run_id=run_id)
            copy = CopyOutput(**result["copy"])
            design = DesignOutput(**result["design"])
            pipeline = MarketingPipeline()
            publish_out = pipeline.publisher.run(
                brief.red_social,
                copy,
                design,
                idempotency_key=run.idempotency_key,
                content_format=_normalize_content_format(getattr(run, "content_format", None)),
            )
            result["publish_result"] = publish_out.model_dump()
        elif go_outcome == "failed" and not result.get("publish_result"):
            raise ValueError(
                "Meta rechazó la publicación (imagen aún procesándose o error Graph API). "
                "Espera 30 segundos y pulsa Aprobar una sola vez — no uses fallback dual."
            )

        if not result.get("publish_result"):
            raise ValueError("No se pudo publicar en la red social")

        run.approved_at = datetime.utcnow()
        run.approved_by = approved_by
        _persist_result(db, run, result, brief.red_social)
        db.commit()
        db.refresh(run)
        logger.info("pipeline.approved_and_published", run_id=run_id, approved_by=approved_by)
        return result
    except Exception:
        run.status = "pending_approval"
        db.commit()
        raise


def reject_run(db: Session, run_id: int, *, reason: str = "", approved_by: str = "human") -> None:
    """Marca el run como rechazado y opcionalmente guarda el motivo en `error_message`."""
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
