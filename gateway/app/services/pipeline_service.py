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

_NATIVE_PYTHON_PLATFORMS: frozenset[str] = frozenset({"linkedin"})


def _publish_via_linkedin(
    db: Session,
    result: dict,
    brief: Brief,
    run: AgentRun,
    idempotency_key: str | None,
) -> str:
    """Publicación nativa LinkedIn con imagen: lee token OAuth de DB y llama al provider Python."""
    from agents.marketing_agents.social_providers import publish_post

    token_row = db.execute(
        select(OAuthToken).where(
            OAuthToken.tenant_id == run.tenant_id,
            OAuthToken.provider == "linkedin",
        )
    ).scalar_one_or_none()

    if not token_row:
        raise ValueError(
            "No hay cuenta de LinkedIn conectada para este tenant. "
            "Conéctala desde el dashboard en Integraciones → Conectar LinkedIn."
        )

    copy_text = result["copy"]["copy_final"]
    image_url = result["design"]["image_url"]

    # Normalizar URL: si apunta a localhost, usar PUBLIC_IMAGE_BASE_URL
    public_base = get_settings().public_image_base_url.rstrip("/")
    if image_url.startswith("http://localhost:8000") and public_base != "http://localhost:8000":
        image_url = image_url.replace("http://localhost:8000", public_base, 1)

    pub = publish_post(
        brief.red_social,
        copy_text,
        image_url,
        idempotency_key,
        content_format=_normalize_content_format(getattr(run, "content_format", None)),
        linkedin_token=token_row.access_token,
        linkedin_urn=token_row.account_id,
    )
    result["publish_result"] = pub
    logger.info("linkedin.publish.ok", post_id=pub.get("platform_post_id"))
    return "success"


def _publish_run(
    db: Session,
    result: dict,
    brief: Brief,
    run: AgentRun,
    idempotency_key: str | None,
) -> str:
    """Enruta publicación: LinkedIn nativo (Python) o Go sidecar (Meta/IG)."""
    platform = brief.red_social.lower()
    if platform in _NATIVE_PYTHON_PLATFORMS:
        return _publish_via_linkedin(db, result, brief, run, idempotency_key)
    return _publish_via_go(result, brief, idempotency_key, run, db)


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
        logger.warning(
            "go_publisher.no_oauth_token",
            platform=platform,
            oauth_provider=oauth_provider,
            tenant_id=run.tenant_id,
        )
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
    """Normaliza el formato de publicación a `feed`/`story`/`reel` (valores desconocidos → feed)."""
    v = (value or "feed").lower()
    return v if v in ("feed", "story", "reel") else "feed"


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
    archetype_override: str | None = None,
    user_asset_url: str | None = None,
    alter_image_with_ai: bool = False,
    visual_instructions: str | None = None,
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
            archetype_override=archetype_override,
            user_asset_url=user_asset_url,
            alter_image_with_ai=alter_image_with_ai,
            visual_instructions=visual_instructions,
        )
        run.result_json = json.dumps(result, ensure_ascii=True)
        run.status = "pending_approval"
        db.add(run)
        db.commit()
        _notify_slack(get_settings().slack_webhook_url, run.id, brief.tema)
        logger.info("pipeline.pending_approval", run_id=run.id)
        return result

    # Sin aprobación requerida: generar contenido; publicación vía _publish_run.
    result = pipeline.run(
        brief_in,
        publish=False,
        idempotency_key=idempotency_key,
        content_format=content_format,
        image_provider=image_provider,
        archetype_override=archetype_override,
        user_asset_url=user_asset_url,
        alter_image_with_ai=alter_image_with_ai,
        visual_instructions=visual_instructions,
    )

    if publish and result.get("quality", {}).get("approved", False):
        _publish_run(db, result, brief, run, idempotency_key)

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
        go_outcome = _publish_run(db, result, brief, run, run.idempotency_key)

        if go_outcome == "unavailable" and not result.get("publish_result"):
            raise ValueError(
                "No se pudo publicar. Para LinkedIn: verifica que la cuenta esté conectada en Integraciones. "
                "Para Meta/IG: verifica que el sidecar Go (:8088) esté activo."
            )
        if go_outcome == "failed" and not result.get("publish_result"):
            raise ValueError(
                "La API nativa rechazó la publicación. "
                "Espera unos segundos y pulsa Aprobar una sola vez."
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
