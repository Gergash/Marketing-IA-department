"""Webhook de Meta para DMs: verificación, firma HMAC, ecos, dedupe por mid y resolución de cuenta."""

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gateway.app.api import webhooks_meta
from gateway.app.db.session import Base, get_db
from gateway.app.models import DmContact, DmMessage, OAuthToken

SECRET = "test-app-secret"
IG_ID = "17841400000000001"
PAGE_ID = "100000000000001"


@pytest.fixture
def env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("META_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "verify-me")
    engine = create_engine(f"sqlite:///{tmp_path / 'webhook_test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(webhooks_meta.router)
    app.dependency_overrides[get_db] = _db

    enqueued: list[tuple[int, int]] = []
    monkeypatch.setattr(webhooks_meta, "_enqueue_agent_turn", lambda c, m: enqueued.append((c, m)))

    with Session() as s:
        s.add(OAuthToken(
            tenant_id="tenant-a",
            provider="meta",
            access_token="page-token",
            account_id=IG_ID,
            account_name="marca_a",
            page_id=PAGE_ID,
            dm_agent_enabled=True,
        ))
        s.commit()
    return TestClient(app), Session, enqueued


def _signed_post(client: TestClient, payload: dict, secret: str = SECRET):
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/api/webhooks/meta",
        content=raw,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )


def _ig_payload(mid: str = "mid.1", text: str = "Hola, quiero info", *, echo: bool = False, recipient: str = IG_ID) -> dict:
    message = {"mid": mid, "text": text}
    if echo:
        message["is_echo"] = True
    return {
        "object": "instagram",
        "entry": [{
            "id": recipient,
            "time": 1760000000000,
            "messaging": [{
                "sender": {"id": "igsid-123"},
                "recipient": {"id": recipient},
                "timestamp": 1760000000000,
                "message": message,
            }],
        }],
    }


def test_verify_signature_accepts_valid_and_rejects_tampered() -> None:
    body = b'{"object":"instagram"}'
    good = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert webhooks_meta.verify_signature(body, good, SECRET)
    assert not webhooks_meta.verify_signature(body + b" ", good, SECRET)
    assert not webhooks_meta.verify_signature(body, None, SECRET)
    assert not webhooks_meta.verify_signature(body, good, "")


def test_get_verification_returns_challenge(env) -> None:
    client, _, _ = env
    ok = client.get("/api/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
    assert ok.status_code == 200
    assert ok.text == "42"
    bad = client.get("/api/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_post_rejects_bad_signature(env) -> None:
    client, Session, enqueued = env
    resp = _signed_post(client, _ig_payload(), secret="otro-secreto")
    assert resp.status_code == 403
    with Session() as s:
        assert s.execute(select(DmMessage)).first() is None
    assert enqueued == []


def test_post_stores_message_and_enqueues_agent(env) -> None:
    client, Session, enqueued = env
    resp = _signed_post(client, _ig_payload())
    assert resp.status_code == 200
    assert resp.json()["received"] == 1
    with Session() as s:
        contact = s.execute(select(DmContact)).scalar_one()
        assert contact.tenant_id == "tenant-a"
        assert contact.platform == "instagram"
        assert contact.sender_id == "igsid-123"
        assert contact.status == "nuevo"
        msg = s.execute(select(DmMessage)).scalar_one()
        assert msg.direction == "in" and msg.text == "Hola, quiero info"
        assert enqueued == [(contact.id, msg.id)]


def test_duplicate_mid_is_ignored(env) -> None:
    client, Session, enqueued = env
    _signed_post(client, _ig_payload(mid="mid.dup"))
    resp = _signed_post(client, _ig_payload(mid="mid.dup"))
    assert resp.json()["received"] == 0
    with Session() as s:
        assert len(s.execute(select(DmMessage)).all()) == 1
    assert len(enqueued) == 1


def test_echo_and_unknown_recipient_are_ignored(env) -> None:
    client, Session, enqueued = env
    assert _signed_post(client, _ig_payload(mid="mid.echo", echo=True)).json()["received"] == 0
    assert _signed_post(client, _ig_payload(mid="mid.x", recipient="999")).json()["received"] == 0
    with Session() as s:
        assert s.execute(select(DmMessage)).first() is None
    assert enqueued == []


def test_messenger_resolves_by_page_id(env) -> None:
    client, Session, _ = env
    payload = {
        "object": "page",
        "entry": [{
            "id": PAGE_ID,
            "messaging": [{
                "sender": {"id": "psid-9"},
                "recipient": {"id": PAGE_ID},
                "timestamp": 1760000000000,
                "message": {"mid": "m_abc", "attachments": [{"type": "image"}]},
            }],
        }],
    }
    assert _signed_post(client, payload).json()["received"] == 1
    with Session() as s:
        contact = s.execute(select(DmContact)).scalar_one()
        assert contact.platform == "messenger"
        assert s.execute(select(DmMessage.text)).scalar_one() == "[envió image]"


def test_agent_disabled_stores_but_does_not_enqueue(env) -> None:
    client, Session, enqueued = env
    with Session() as s:
        acc = s.execute(select(OAuthToken)).scalar_one()
        acc.dm_agent_enabled = False
        s.commit()
    assert _signed_post(client, _ig_payload(mid="mid.off")).json()["received"] == 1
    assert enqueued == []
