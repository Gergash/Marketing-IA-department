"""Bold checkout, webhook y consulta de créditos (staging SaaS)."""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.core.auth import require_auth
from gateway.app.core.settings import get_settings
from gateway.app.db.session import get_db
from gateway.app.models.entities import PaymentRecord
from gateway.app.payment.bold_client import (
    integrity_signature,
    parse_bold_event,
    verify_webhook_signature,
)
from gateway.app.services.credits_service import (
    COST_AI_IMAGE,
    COST_REEL,
    COST_STATIC_IMAGE,
    COST_USER_IMAGE_DESIGN,
    COST_VIDEO_SUBTITLES,
    add_credits,
    get_or_create_wallet,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])
_log = structlog.get_logger(__name__)


class BoldCheckoutResponse(BaseModel):
    order_id: str
    amount_cop: int
    currency: str
    api_key: str
    integrity_signature: str
    description: str
    redirection_url: str
    credits_per_pack: int


class CreditsStatusResponse(BaseModel):
    tenant_id: str
    balance: int
    pack_amount_cop: int
    credits_per_pack: int
    costs: dict[str, int]
    show_bold_button: bool


class WebhookResponse(BaseModel):
    success: bool
    message: str
    reference: str = ""
    credits_added: int = 0
    already_processed: bool = False


def _ensure_staging() -> None:
    if not get_settings().staging_saas_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing SaaS inactivo.")


@router.get("/credits", response_model=CreditsStatusResponse)
def credits_status(
    tenant_id: str = Depends(require_auth),
    db: Session = Depends(get_db),
) -> CreditsStatusResponse:
    s = get_settings()
    wallet = get_or_create_wallet(db, tenant_id)
    return CreditsStatusResponse(
        tenant_id=tenant_id,
        balance=wallet.balance,
        pack_amount_cop=s.pack_amount_cop,
        credits_per_pack=s.credits_per_pack,
        costs={
            "static_image": COST_STATIC_IMAGE,
            "ai_image": COST_AI_IMAGE,
            "user_image_design": COST_USER_IMAGE_DESIGN,
            "video_subtitles": COST_VIDEO_SUBTITLES,
            "reel": COST_REEL,
        },
        show_bold_button=s.staging_saas_enabled,
    )


@router.get("/bold-checkout", response_model=BoldCheckoutResponse)
def bold_checkout(tenant_id: str = Depends(require_auth)) -> BoldCheckoutResponse:
    _ensure_staging()
    s = get_settings()
    api_key = (s.bold_api_key or "").strip()
    secret = (s.bold_integrity_secret or "").strip()
    if not api_key or not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bold no configurado: faltan BOLD_API_KEY o BOLD_INTEGRITY_SECRET.",
        )

    amount = max(1000, int(s.pack_amount_cop or 99000))
    currency = "COP"
    order_id = f"MDIA-{tenant_id}-{int(time.time())}"
    description = f"Marketing DEPA IA — créditos tenant={tenant_id}"
    redirect = (s.staging_success_redirect_url or "http://localhost:5173/app").strip()
    sep = "&" if "?" in redirect else "?"
    redirection_url = f"{redirect}{sep}tenant_id={tenant_id}"

    sig = integrity_signature(order_id, amount, currency, secret)
    return BoldCheckoutResponse(
        order_id=order_id,
        amount_cop=amount,
        currency=currency,
        api_key=api_key,
        integrity_signature=sig,
        description=description,
        redirection_url=redirection_url,
        credits_per_pack=s.credits_per_pack,
    )


@router.post("/bold-webhook", response_model=WebhookResponse)
async def bold_webhook(request: Request, db: Session = Depends(get_db)) -> WebhookResponse:
    _ensure_staging()
    s = get_settings()
    raw = await request.body()
    signature = request.headers.get("X-Bold-Signature", "")
    webhook_secret = (s.bold_webhook_secret or s.bold_integrity_secret or "").strip()

    if webhook_secret and not verify_webhook_signature(raw, signature, webhook_secret):
        _log.warning("bold.webhook.invalid_signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma Bold inválida.")

    event = parse_bold_event(raw)
    ref = (event.get("reference") or "").strip()
    if not ref:
        ref = f"bold-unknown-{int(time.time())}"

    existing = db.execute(select(PaymentRecord).where(PaymentRecord.reference == ref)).scalar_one_or_none()
    if existing and existing.status == "paid":
        return WebhookResponse(
            success=True,
            message="Pago ya procesado.",
            reference=ref,
            credits_added=existing.credits_added,
            already_processed=True,
        )

    if not event.get("ok"):
        if existing:
            existing.status = "failed"
            db.commit()
        else:
            db.add(
                PaymentRecord(
                    tenant_id=event.get("tenant_id") or "unknown",
                    reference=ref,
                    amount_cop=int(event.get("amount_cop") or 0),
                    status="failed",
                    payer_email=event.get("payer_email") or None,
                )
            )
            db.commit()
        return WebhookResponse(success=False, message="Evento Bold no exitoso.", reference=ref)

    tenant_id = str(event.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se encontró tenant_id en reference/description.",
        )

    amount_cop = int(event.get("amount_cop") or 0)
    expected = int(s.pack_amount_cop or 99000)
    if amount_cop and amount_cop != expected:
        _log.warning("bold.webhook.amount_mismatch", got=amount_cop, expected=expected, ref=ref)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Monto inválido: se esperaban ${expected:,} COP.",
        )

    credits = int(s.credits_per_pack or 100)
    if existing:
        existing.status = "paid"
        existing.tenant_id = tenant_id
        existing.amount_cop = amount_cop or expected
        existing.credits_added = credits
        existing.payer_email = event.get("payer_email") or existing.payer_email
    else:
        db.add(
            PaymentRecord(
                tenant_id=tenant_id,
                reference=ref,
                amount_cop=amount_cop or expected,
                credits_added=credits,
                status="paid",
                payer_email=event.get("payer_email") or None,
            )
        )
    db.commit()

    wallet = add_credits(db, tenant_id, credits)
    _log.info("bold.webhook.credits_added", tenant_id=tenant_id, credits=credits, balance=wallet.balance)
    return WebhookResponse(
        success=True,
        message=f"Se acreditaron {credits} créditos.",
        reference=ref,
        credits_added=credits,
    )
