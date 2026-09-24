"""Telemetría de uso de proveedores externos (imagen/video/voz/transcripción) por tenant."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gateway.app.models.entities import ApiUsageEvent


def record_usage(
    db: Session,
    tenant_id: str,
    provider: str,
    operation: str,
    *,
    run_id: int | str | None = None,
    model: str = "",
    units: int = 1,
    credits_cost: int = 0,
    success: bool = True,
) -> ApiUsageEvent:
    event = ApiUsageEvent(
        tenant_id=tenant_id,
        run_id=str(run_id) if run_id is not None else None,
        provider=(provider or "unknown").strip().lower(),
        operation=operation,
        model=model or "",
        units=units,
        credits_cost=credits_cost,
        success=success,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def usage_by_provider(
    db: Session,
    *,
    tenant_id: str | None = None,
    since: datetime | None = None,
    exclude_providers: tuple[str, ...] = (),
) -> list[dict]:
    """Reparto de uso por proveedor. `share_pct` es sobre el conteo de eventos (volumen de uso)."""
    q = select(
        ApiUsageEvent.provider,
        func.count(ApiUsageEvent.id),
        func.coalesce(func.sum(ApiUsageEvent.units), 0),
        func.coalesce(func.sum(ApiUsageEvent.credits_cost), 0),
    ).group_by(ApiUsageEvent.provider)
    if tenant_id:
        q = q.where(ApiUsageEvent.tenant_id == tenant_id)
    if since:
        q = q.where(ApiUsageEvent.created_at >= since)
    if exclude_providers:
        q = q.where(ApiUsageEvent.provider.notin_(exclude_providers))
    rows = db.execute(q).all()
    total_events = sum(r[1] for r in rows) or 1
    return [
        {
            "provider": r[0],
            "events": int(r[1]),
            "units": int(r[2]),
            "credits": int(r[3]),
            "share_pct": round(r[1] * 100.0 / total_events, 2),
        }
        for r in rows
    ]


def usage_totals(
    db: Session,
    *,
    tenant_id: str | None = None,
    since: datetime | None = None,
) -> dict:
    q = select(
        func.count(ApiUsageEvent.id),
        func.coalesce(func.sum(ApiUsageEvent.units), 0),
        func.coalesce(func.sum(ApiUsageEvent.credits_cost), 0),
    )
    if tenant_id:
        q = q.where(ApiUsageEvent.tenant_id == tenant_id)
    if since:
        q = q.where(ApiUsageEvent.created_at >= since)
    events, units, credits = db.execute(q).one()
    return {"events": int(events), "units": int(units), "credits": int(credits)}
