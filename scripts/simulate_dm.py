"""Simula un DM entrante firmado como Meta contra el webhook local (staging).

Uso (desde la raíz del repo, con la API arriba en :8000):
    python scripts/simulate_dm.py "Hola, quiero cotizar un apartamento"
    python scripts/simulate_dm.py "Me llamo Ana" --sender ana-test
    python scripts/simulate_dm.py "Hola" --platform messenger

Usa la primera cuenta Meta activa de la BD (o --account-id). Con DM_AGENT_DRY_RUN=true
la respuesta del agente queda en la Bandeja sin llamar a Meta.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from gateway.app.core.settings import get_settings  # noqa: E402
from gateway.app.db.session import SessionLocal  # noqa: E402
from gateway.app.models import OAuthToken  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("text")
    parser.add_argument("--sender", default="staging-tester-1", help="ID del remitente simulado (una conversación por ID)")
    parser.add_argument("--platform", choices=("instagram", "messenger"), default="instagram")
    parser.add_argument("--account-id", type=int, help="oauth_tokens.id (por defecto la primera cuenta Meta activa)")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    s = get_settings()
    secret = (s.meta_client_secret or s.meta_app_secret or "").strip()
    if not secret:
        print("Falta META_CLIENT_SECRET / META_APP_SECRET en el entorno.")
        return 1

    with SessionLocal() as db:
        stmt = select(OAuthToken).where(OAuthToken.provider == "meta", OAuthToken.is_active.is_(True))
        if args.account_id:
            stmt = stmt.where(OAuthToken.id == args.account_id)
        account = db.execute(stmt.order_by(OAuthToken.id).limit(1)).scalar_one_or_none()
    if account is None:
        print("No hay cuenta Meta conectada en esta BD: entra al estudio y usa Integraciones → Conectar Meta.")
        return 1
    recipient = account.account_id if args.platform == "instagram" else account.page_id
    if not recipient:
        print("La cuenta no tiene page_id: Messenger no aplica para ella.")
        return 1

    now_ms = int(time.time() * 1000)
    payload = {
        "object": "instagram" if args.platform == "instagram" else "page",
        "entry": [{
            "id": recipient,
            "time": now_ms,
            "messaging": [{
                "sender": {"id": args.sender},
                "recipient": {"id": recipient},
                "timestamp": now_ms,
                "message": {"mid": f"sim.{uuid.uuid4().hex}", "text": args.text},
            }],
        }],
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    r = httpx.post(
        f"{args.api.rstrip('/')}/api/webhooks/meta",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        timeout=15,
    )
    print(f"{r.status_code} {r.text}")
    print(f"Cuenta: {account.account_name or account.id} · agente {'activo' if account.dm_agent_enabled else 'APAGADO'}")
    return 0 if r.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
