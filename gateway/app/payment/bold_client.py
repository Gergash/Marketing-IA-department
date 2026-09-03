"""Bold: firma de integridad del botón y verificación de webhook (patrón Malcom/InsightFlow)."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

_TENANT_ORDER = re.compile(r"^MDIA-([a-zA-Z0-9_-]+)-\d+$", re.I)
_SUCCESS = frozenset({"approved", "completed", "paid", "successful", "success", "succeeded"})


def integrity_signature(order_id: str, amount_cop: int, currency: str, secret_key: str) -> str:
    """SHA256(orderId + amount + currency + secretKey) en hex."""
    cadena = f"{order_id}{amount_cop}{currency}{secret_key}"
    return hashlib.sha256(cadena.encode()).hexdigest()


def verify_webhook_signature(raw: bytes, provided_header: str, webhook_secret: str) -> bool:
    secret = (webhook_secret or "").strip()
    provided = (provided_header or "").strip().removeprefix("sha256=")
    if not secret or not provided:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    try:
        import base64

        if all(c in "0123456789abcdef" for c in provided.lower()) and len(provided) % 2 == 0:
            decoded = bytes.fromhex(provided)
            return hmac.compare_digest(decoded, expected)
        decoded = base64.b64decode(provided)
        return hmac.compare_digest(decoded, expected)
    except Exception:
        return hmac.compare_digest(expected.hex(), provided.lower())


def _dig(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _normalize_amount(raw: Any) -> int:
    if raw is None:
        return 0
    if isinstance(raw, int):
        return raw if raw > 1000 else raw * 100  # heurística cents vs COP
    try:
        val = int(float(raw))
        return val if val > 1000 else val * 100
    except (TypeError, ValueError):
        return 0


def parse_bold_event(raw: bytes) -> dict[str, Any]:
    """Extrae estado, referencia, monto y tenant_id del webhook Bold."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {"ok": False, "status": "", "reference": "", "amount_cop": 0, "tenant_id": ""}

    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    tx = nested.get("transaction") if isinstance(nested.get("transaction"), dict) else {}
    pay = nested.get("payment") if isinstance(nested.get("payment"), dict) else {}

    status = str(
        _dig(data, "status")
        or _dig(nested, "status")
        or _dig(tx, "status")
        or _dig(pay, "status")
        or ""
    ).lower()
    reference = str(
        _dig(data, "reference", "order_id")
        or _dig(nested, "reference", "order_id")
        or _dig(tx, "reference", "id")
        or _dig(pay, "reference", "id")
        or ""
    ).strip()
    description = str(
        _dig(data, "description") or _dig(nested, "description") or _dig(tx, "description") or ""
    )
    amount_raw = _dig(data, "amount", "amount_in_cents") or _dig(nested, "amount") or _dig(tx, "amount")
    amount_cop = _normalize_amount(amount_raw)
    if amount_cop > 100000:
        amount_cop = amount_cop // 100

    tenant_id = extract_tenant_id(reference, description, json.dumps(data))
    return {
        "ok": status in _SUCCESS,
        "status": status,
        "reference": reference,
        "amount_cop": amount_cop,
        "tenant_id": tenant_id,
        "payer_email": str(_dig(data, "payer_email", "email") or _dig(nested, "payer_email") or "").strip(),
    }


def extract_tenant_id(reference: str, description: str, blob: str = "") -> str:
    for candidate in (reference, description, blob):
        m = _TENANT_ORDER.search(candidate or "")
        if m:
            return m.group(1)
        m2 = re.search(r"tenant_id[=:]([a-zA-Z0-9_-]+)", candidate or "", re.I)
        if m2:
            return m2.group(1)
    return ""
