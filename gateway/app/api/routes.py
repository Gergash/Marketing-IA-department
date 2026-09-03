"""Endpoints REST bajo el prefijo `/api` (briefs, runs, campañas, salud)."""

import json

import kombu.exceptions
import redis
import redis.exceptions
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.marketing_agents.thought_stream import (
    RunCancelledByUser,
    push_reply,
    read_events,
    supports_cross_process,
)
from gateway.app.core.auth import require_auth
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models import AgentRun, Brief, CampaignSchedule
from gateway.app.schemas.contracts import (
    AdvisorChatRequest,
    AdvisorChatResponse,
    ApproveRequest,
    ArchetypeInfo,
    BrandManualResponse,
    BriefCreate,
    BriefResponse,
    CampaignFireResponse,
    CampaignScheduleCreate,
    CampaignScheduleResponse,
    ContentFormatsResponse,
    ImageProvidersResponse,
    JobStatusResponse,
    RejectRequest,
    ReviseRequest,
    RunRequest,
    RunResponse,
    SocialPublishStatusResponse,
    ThoughtReplyRequest,
    VideoOptionsResponse,
    ThoughtReplyResponse,
    ThoughtsResponse,
    UploadAssetResponse,
)
from gateway.app.services.pipeline_service import (
    approve_run,
    create_run,
    execute_pipeline,
    prepare_revision,
    reject_run,
    revise_run,
)
from gateway.app.services.scheduler_service import fire_campaign_by_id, sync_campaign_jobs
from workers.celery_app import celery_app
from workers.tasks import execute_pipeline_task, execute_video_pipeline_task

router = APIRouter(prefix="/api")


def _raise_from_domain_error(exc: ValueError) -> None:
    msg = str(exc)
    if "Créditos insuficientes" in msg:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=msg) from exc
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc


@router.get("/social/publish-status", response_model=SocialPublishStatusResponse)
def social_publish_status(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> SocialPublishStatusResponse:
    """Indica qué integraciones de publicación están configuradas (sin exponer secretos)."""
    s = get_settings()
    from sqlalchemy import select

    from gateway.app.models import OAuthToken

    oauth_rows = db.execute(
        select(OAuthToken.provider).where(OAuthToken.tenant_id == tenant_id)
    ).scalars().all()
    oauth_set = set(oauth_rows)
    linkedin_oauth = "linkedin" in oauth_set
    meta_oauth = "meta" in oauth_set
    x_oauth = "x" in oauth_set
    return SocialPublishStatusResponse(
        social_provider=s.social_provider,
        linkedin_ready=bool(s.linkedin_access_token.strip()) or linkedin_oauth,
        linkedin_oauth_connected=linkedin_oauth,
        x_app_configured=bool(s.x_api_key.strip() and s.x_api_secret.strip()),
        x_oauth_connected=x_oauth
        or bool(s.x_access_token.strip() and s.x_access_token_secret.strip()),
        meta_oauth_connected=meta_oauth,
        meta_instagram_ready=bool(
            s.meta_page_access_token.strip() and s.instagram_business_account_id.strip()
        )
        or meta_oauth,
        go_publisher_url=s.go_publisher_url,
    )


@router.get("/image/archetypes", response_model=list[ArchetypeInfo])
def list_archetypes(
    tenant_id: str = Depends(require_auth),
) -> list[ArchetypeInfo]:
    """Lista los arquetipos de layout editorial disponibles para override manual en un run."""
    _ = tenant_id
    from agents.marketing_agents.layout_archetypes import _ARCHETYPE_MAP
    return [ArchetypeInfo(id=a.id, label=a.label) for a in _ARCHETYPE_MAP.values()]


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
    if s.venice_api_key.strip():
        model = (s.venice_image_model or "venice-sd35").strip()
        providers.append(
            {
                "id": "venice",
                "label": f"Venice.ai ({model})",
            }
        )
    return ImageProvidersResponse(
        default_provider=s.image_provider,
        providers=providers,
    )


@router.get("/image/formats", response_model=ContentFormatsResponse)
def content_formats(
    tenant_id: str = Depends(require_auth),
) -> ContentFormatsResponse:
    """Formatos de publicación disponibles por red social (dimensiones incluidas)."""
    _ = tenant_id
    from agents.marketing_agents.image_specs import NETWORKS, formats_for_network

    return ContentFormatsResponse(
        networks=[{"id": net_id, "label": label} for net_id, label in NETWORKS],
        formats_by_network={net_id: formats_for_network(net_id) for net_id, _label in NETWORKS},
    )


@router.get("/video/options", response_model=VideoOptionsResponse)
def video_options(
    tenant_id: str = Depends(require_auth),
) -> VideoOptionsResponse:
    """Modos y modelos Venice para Reels (sin secretos)."""
    _ = tenant_id
    from agents.marketing_agents.venice_video_models import VENICE_VIDEO_MODEL_OPTIONS

    s = get_settings()
    return VideoOptionsResponse(
        default_mode=(s.video_gen_mode or "scenes").strip() or "scenes",
        default_model=(s.venice_video_model or "seedance-2.0").strip() or "seedance-2.0",
        modes=[
            {
                "id": "full",
                "label": "Clip AI completo (Venice genera todo el video)",
            },
            {
                "id": "scenes",
                "label": "Unir tomas AI (Venice por escena + Shotstack)",
            },
            {
                "id": "still",
                "label": "Stills + Ken Burns (Shotstack, sin Venice video)",
            },
        ],
        models=VENICE_VIDEO_MODEL_OPTIONS,
        venice_configured=bool(s.venice_api_key.strip()),
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


@router.post("/briefs/upload-asset", response_model=UploadAssetResponse)
async def upload_brief_asset(
    file: UploadFile = File(...),
    tenant_id: str = Depends(require_auth),
) -> UploadAssetResponse:
    """Sube foto del usuario a static/uploads/ para Design-as-Code (capa base intacta)."""
    _ = tenant_id
    from agents.marketing_agents.user_assets import (
        ALLOWED_UPLOAD_MIME,
        MAX_UPLOAD_BYTES,
        local_url_for_upload,
        uploads_dir,
    )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_UPLOAD_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo no permitido: {content_type}. Usa JPEG, PNG o WebP.",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo demasiado grande (máx {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío")

    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(content_type, ".bin")
    import uuid

    filename = f"{uuid.uuid4().hex}{ext}"
    dest = uploads_dir() / filename
    dest.write_bytes(data)

    return UploadAssetResponse(
        url=local_url_for_upload(filename),
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
    )


@router.post("/briefs/upload-brand-manual", response_model=BrandManualResponse)
async def upload_brand_manual(
    file: UploadFile = File(...),
    tenant_id: str = Depends(require_auth),
) -> BrandManualResponse:
    """Sube el PDF del manual de marca; extrae texto e inyecta en agentes del tenant."""
    from agents.marketing_agents.brand_manual import (
        ALLOWED_BRAND_MIME,
        MAX_BRAND_BYTES,
        save_brand_manual,
    )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    # Algunos navegadores mandan application/octet-stream; validamos extensión también.
    name = (file.filename or "manual.pdf").strip()
    if content_type not in ALLOWED_BRAND_MIME and not name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo no permitido: {content_type}. Sube un PDF del manual de marca.",
        )

    data = await file.read()
    if len(data) > MAX_BRAND_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo demasiado grande (máx {MAX_BRAND_BYTES // (1024 * 1024)} MB)",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío")

    try:
        meta = save_brand_manual(tenant_id, data, original_filename=name)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return BrandManualResponse(
        id=meta["id"],
        url=meta["url"],
        original_filename=meta["original_filename"],
        char_count=meta["char_count"],
        text_preview=meta.get("text_preview") or "",
        extraction_method=meta.get("extraction_method") or "",
        palette_hex=list(meta.get("palette_hex") or []),
        color_roles=dict(meta.get("color_roles") or {}),
        logo_urls=list(meta.get("logo_urls") or []),
        logo_placements=list(meta.get("logo_placements") or []),
        font_names=list(meta.get("font_names") or []),
        layout_hints=list(meta.get("layout_hints") or []),
        suggested_archetype=meta.get("suggested_archetype"),
        pages_scanned=int(meta.get("pages_scanned") or 0),
        embedded_images=int(meta.get("embedded_images") or 0),
    )


@router.get("/briefs/brand-manual", response_model=BrandManualResponse | None)
def get_brand_manual(
    tenant_id: str = Depends(require_auth),
) -> BrandManualResponse | None:
    """Devuelve el manual de marca activo del tenant, o null si no hay."""
    from agents.marketing_agents.brand_manual import get_active_brand_meta, load_brand_text

    meta = get_active_brand_meta(tenant_id)
    if not meta:
        return None
    text = load_brand_text(tenant_id, max_chars=400)
    return BrandManualResponse(
        id=meta["id"],
        url=meta["url"],
        original_filename=meta.get("original_filename") or meta.get("pdf_filename") or "",
        char_count=int(meta.get("char_count") or 0),
        text_preview=(text[:400] + ("…" if len(text) > 400 else "")) if text else "",
        extraction_method=meta.get("extraction_method") or "",
        palette_hex=list(meta.get("palette_hex") or []),
        color_roles=dict(meta.get("color_roles") or {}),
        logo_urls=list(meta.get("logo_urls") or []),
        logo_placements=list(meta.get("logo_placements") or []),
        font_names=list(meta.get("font_names") or []),
        layout_hints=list(meta.get("layout_hints") or []),
        suggested_archetype=meta.get("suggested_archetype"),
        pages_scanned=int(meta.get("pages_scanned") or 0),
        embedded_images=int(meta.get("embedded_images") or 0),
    )


@router.delete("/briefs/brand-manual")
def delete_brand_manual(
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Desactiva el manual de marca del tenant."""
    from agents.marketing_agents.brand_manual import clear_brand_manual

    cleared = clear_brand_manual(tenant_id)
    return {"ok": cleared}


@router.post("/advisor/chat", response_model=AdvisorChatResponse)
def advisor_chat(
    payload: AdvisorChatRequest,
    tenant_id: str = Depends(require_auth),
) -> AdvisorChatResponse:
    """Asesor creativo (diseñador + productor + mercadólogo) en burbuja de chat."""
    from agents.marketing_agents.advisor import CreativeAdvisorAgent

    reply = CreativeAdvisorAgent().reply(
        payload.message,
        tenant_id=tenant_id,
        history=payload.history,
        brief_context=payload.brief_context,
    )
    return AdvisorChatResponse(reply=reply)


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


def _run_params(payload: RunRequest, *, interactive: bool | None = None) -> dict:
    """Configuración visual del run que una revisión posterior debe poder reproducir."""
    return {
        "publish": payload.publish,
        "trace_id": payload.trace_id,
        "interactive": payload.interactive if interactive is None else interactive,
        "image_provider": payload.image_provider,
        "archetype_override": payload.archetype_override,
        "user_asset_url": payload.user_asset_url,
        "alter_image_with_ai": payload.alter_image_with_ai,
        "visual_instructions": payload.visual_instructions,
        "drive_folder_id": payload.drive_folder_id,
        "social_account_id": payload.social_account_id,
        "link_url": payload.link_url,
        "cta_on_image": payload.cta_on_image,
        "video_gen_mode": payload.video_gen_mode,
        "venice_video_model": payload.venice_video_model,
    }


@router.post("/runs/sync", response_model=RunResponse)
def run_pipeline_sync(
    payload: RunRequest,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> RunResponse:
    """Ejecuta el pipeline de agentes de forma síncrona en el mismo proceso que la API."""
    if payload.content_format in ("reel", "user_clip_reel"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"content_format='{payload.content_format}' requiere ejecucion async "
                "(POST /api/runs/async): el render de video puede tardar varios minutos."
            ),
        )
    run = create_run(
        db,
        brief_id=payload.brief_id,
        tenant_id=tenant_id,
        run_mode="sync",
        idempotency_key=payload.idempotency_key,
        content_format=payload.content_format,
        params=_run_params(payload),
        social_account_id=payload.social_account_id,
    )
    try:
        result = execute_pipeline(
            db,
            run.id,
            publish=payload.publish,
            requires_approval=payload.requires_approval,
            idempotency_key=payload.idempotency_key,
            image_provider=payload.image_provider,
            archetype_override=payload.archetype_override,
            user_asset_url=payload.user_asset_url,
            alter_image_with_ai=payload.alter_image_with_ai,
            visual_instructions=payload.visual_instructions,
            drive_folder_id=payload.drive_folder_id,
        )
    except RunCancelledByUser:
        # Detener desde un checkpoint es decisión del usuario, no un fallo: el run ya
        # quedó `rejected` en el servicio, así que se responde 200 en vez de 500.
        return RunResponse(run_id=run.id, status="rejected")
    except ValueError as exc:
        _raise_from_domain_error(exc)
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
        # Sin Redis los eventos viven en la memoria de este proceso: el worker de Celery
        # nunca vería las respuestas y se quedaría esperando hasta agotar el plazo.
        params=_run_params(payload, interactive=payload.interactive and supports_cross_process()),
        social_account_id=payload.social_account_id,
    )
    is_video = payload.content_format in ("reel", "user_clip_reel")
    task = execute_video_pipeline_task if is_video else execute_pipeline_task
    apply_async_kwargs: dict = {
        "args": [
            run.id,
            payload.publish,
            payload.requires_approval,
            payload.idempotency_key,
            payload.image_provider,
        ],
        "kwargs": {
            "archetype_override": payload.archetype_override,
            "user_asset_url": payload.user_asset_url,
            "alter_image_with_ai": payload.alter_image_with_ai,
            "visual_instructions": payload.visual_instructions,
            "drive_folder_id": payload.drive_folder_id,
        },
    }
    if is_video:
        # Renders pueden tardar minutos: cola dedicada para no bloquear la cola de imagenes.
        apply_async_kwargs["queue"] = "video_render"
    try:
        task.apply_async(**apply_async_kwargs)
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
        _raise_from_domain_error(exc)
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


@router.post("/runs/{run_id}/revise", response_model=RunResponse)
def revise_run_endpoint(
    run_id: int,
    payload: ReviseRequest,
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> RunResponse:
    """Regenera la pieza de un run pendiente aplicando las notas del revisor; vuelve a pending_approval."""
    run = db.get(AgentRun, run_id)
    if not run or run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")

    content_format = getattr(run, "content_format", "feed") or "feed"
    if content_format not in ("reel", "user_clip_reel"):
        try:
            result = revise_run(
                db,
                run_id,
                notes=payload.notes,
                revised_by=payload.revised_by,
                trace_id=payload.trace_id,
                interactive=payload.interactive,
            )
        except RunCancelledByUser:
            return RunResponse(run_id=run_id, status="rejected")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except Exception as exc:
            # La versión anterior sigue en result_json y sigue siendo aprobable: devolver el run
            # a pending_approval en vez de dejarlo 'failed' (que bloquearía aprobar y reintentar).
            run.status = "pending_approval"
            run.error_message = f"revision_failed: {exc}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
            ) from exc
        return RunResponse(run_id=run_id, status="pending_approval", result=result)

    # Los formatos de video tardan minutos: se re-renderizan en la cola dedicada, igual que el run original.
    try:
        params = prepare_revision(
            db,
            run_id,
            notes=payload.notes,
            revised_by=payload.revised_by,
            next_status="queued",
            trace_id=payload.trace_id,
            interactive=payload.interactive and supports_cross_process(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        execute_video_pipeline_task.apply_async(
            args=[run_id, bool(params.get("publish", False)), True, None, params.get("image_provider")],
            kwargs={
                "archetype_override": params.get("archetype_override"),
                "user_asset_url": params.get("user_asset_url"),
                "alter_image_with_ai": bool(params.get("alter_image_with_ai", False)),
                "visual_instructions": params.get("visual_instructions"),
                "drive_folder_id": params.get("drive_folder_id"),
                "revision_notes": payload.notes.strip(),
            },
            queue="video_render",
        )
    except (
        redis.exceptions.ConnectionError,
        kombu.exceptions.OperationalError,
        OSError,
        RuntimeError,
    ) as exc:
        run.status = "pending_approval"
        run.error_message = f"celery_broker_unavailable: {exc}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Redis no esta disponible (broker de Celery); la revision del video no se encolo. "
                "Levanta Redis y el worker de la cola video_render."
            ),
        ) from exc

    return RunResponse(run_id=run_id, status="queued")


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


@router.get("/thoughts/{trace_id}", response_model=ThoughtsResponse)
def get_thoughts(
    trace_id: str,
    since: int = 0,
    tenant_id: str = Depends(require_auth),
) -> ThoughtsResponse:
    """Eventos del hilo de pensamiento a partir de `since` (polling del dashboard).

    `next_since` es el cursor para el siguiente poll; los eventos son inmutables y
    solo se añaden al final, así que basta con el índice.
    """
    _ = tenant_id
    events = read_events(trace_id, since)
    return ThoughtsResponse(
        trace_id=trace_id,
        events=events,
        next_since=max(since, 0) + len(events),
        interactive_supported=supports_cross_process(),
    )


@router.post("/thoughts/{trace_id}/reply", response_model=ThoughtReplyResponse)
def reply_to_thought(
    trace_id: str,
    payload: ThoughtReplyRequest,
    tenant_id: str = Depends(require_auth),
) -> ThoughtReplyResponse:
    """Entrega la decisión del usuario al agente que espera en un checkpoint."""
    _ = tenant_id
    try:
        push_reply(
            trace_id,
            action=payload.action,
            notes=payload.notes,
            checkpoint=payload.checkpoint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ThoughtReplyResponse(
        trace_id=trace_id,
        action=payload.action,
        checkpoint=payload.checkpoint,
    )


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
