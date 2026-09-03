"""Saldo de créditos por tenant y costos por tipo de publicación."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from gateway.app.models.entities import CreditWallet

# Costo en créditos por publicación (staging — ajustable vía env en el futuro)
COST_STATIC_IMAGE = 1
COST_AI_IMAGE = 2
COST_USER_IMAGE_DESIGN = 2
COST_VIDEO_SUBTITLES = 5
COST_REEL = 8


def get_or_create_wallet(db: Session, tenant_id: str) -> CreditWallet:
    row = db.execute(select(CreditWallet).where(CreditWallet.tenant_id == tenant_id)).scalar_one_or_none()
    if row:
        return row
    row = CreditWallet(tenant_id=tenant_id, balance=0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def publish_credit_cost(
    *,
    content_format: str,
    user_asset_url: str | None = None,
    alter_image_with_ai: bool = False,
) -> int:
    fmt = (content_format or "feed").lower()
    if fmt in ("reel", "user_clip_reel"):
        return COST_REEL
    if fmt in ("story",) and user_asset_url:
        return COST_VIDEO_SUBTITLES
    if user_asset_url and not alter_image_with_ai:
        return COST_USER_IMAGE_DESIGN
    if alter_image_with_ai or not user_asset_url:
        return COST_AI_IMAGE
    return COST_STATIC_IMAGE


def debit_for_publish(
    db: Session,
    tenant_id: str,
    cost: int,
) -> CreditWallet:
    wallet = get_or_create_wallet(db, tenant_id)
    if wallet.balance < cost:
        raise ValueError(
            f"Créditos insuficientes: necesitas {cost}, tienes {wallet.balance}. "
            "Recarga con Bold para continuar publicando."
        )
    wallet.balance -= cost
    db.commit()
    db.refresh(wallet)
    return wallet


def add_credits(db: Session, tenant_id: str, amount: int) -> CreditWallet:
    if amount <= 0:
        raise ValueError("amount debe ser positivo")
    wallet = get_or_create_wallet(db, tenant_id)
    wallet.balance += amount
    db.commit()
    db.refresh(wallet)
    return wallet
