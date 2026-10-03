"""API /api/inbox: listado con filtros, aislamiento por tenant, pausa, respuesta manual, toggle y CSV."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from agents.marketing_agents import dm_sender
from gateway.app.api import inbox
from gateway.app.core.auth import require_auth
from gateway.app.db.session import Base, get_db
from gateway.app.models import DmContact, DmMessage, OAuthToken


@pytest.fixture
def env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'inbox_test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(inbox.router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[require_auth] = lambda: "tenant-a"

    now = datetime.utcnow()
    with Session() as s:
        acc = OAuthToken(tenant_id="tenant-a", provider="meta", access_token="tok", account_id="ig-a",
                         account_name="marca_a", page_id="page-a")
        other = OAuthToken(tenant_id="tenant-b", provider="meta", access_token="tok", account_id="ig-b",
                           account_name="marca_b", page_id="page-b")
        s.add_all([acc, other])
        s.flush()
        ana = DmContact(tenant_id="tenant-a", oauth_token_id=acc.id, platform="instagram", sender_id="s1",
                        full_name="Ana Pérez", phone="3001112233", city="Laureles", motive="Arriendo",
                        motive_category="informacion", status="datos_completos", last_message_at=now)
        luis = DmContact(tenant_id="tenant-a", oauth_token_id=acc.id, platform="messenger", sender_id="s2",
                         display_name="Luis", motive="Queja por demora", motive_category="queja",
                         status="requiere_humano", last_message_at=now - timedelta(days=2))
        foreign = DmContact(tenant_id="tenant-b", oauth_token_id=other.id, platform="instagram", sender_id="s3",
                            full_name="Otro Tenant", status="nuevo", last_message_at=now)
        s.add_all([ana, luis, foreign])
        s.flush()
        s.add_all([
            DmMessage(contact_id=ana.id, direction="in", sent_by="contact", text="Hola", meta_mid="a1", created_at=now),
            DmMessage(contact_id=luis.id, direction="in", sent_by="contact", text="Nadie responde", meta_mid="l1",
                      created_at=now - timedelta(days=2)),
        ])
        s.commit()
        ids = {"acc": acc.id, "other": other.id, "ana": ana.id, "luis": luis.id, "foreign": foreign.id}
    return TestClient(app), Session, ids


def test_list_filters_and_tenant_isolation(env) -> None:
    client, _, ids = env
    data = client.get("/api/inbox/contacts").json()
    assert data["total"] == 2
    assert {c["id"] for c in data["items"]} == {ids["ana"], ids["luis"]}
    assert data["counts_by_status"] == {"datos_completos": 1, "requiere_humano": 1}

    only_human = client.get("/api/inbox/contacts", params={"status": "requiere_humano"}).json()
    assert [c["id"] for c in only_human["items"]] == [ids["luis"]]
    by_search = client.get("/api/inbox/contacts", params={"q": "laureles"}).json()
    assert [c["id"] for c in by_search["items"]] == [ids["ana"]]
    assert client.get("/api/inbox/contacts", params={"status": "inventado"}).status_code == 422

    assert client.get(f"/api/inbox/contacts/{ids['foreign']}").status_code == 404


def test_detail_includes_messages_and_window(env) -> None:
    client, _, ids = env
    ana = client.get(f"/api/inbox/contacts/{ids['ana']}").json()
    assert ana["can_reply"] is True
    assert [m["text"] for m in ana["messages"]] == ["Hola"]
    assert client.get(f"/api/inbox/contacts/{ids['luis']}").json()["can_reply"] is False


def test_resume_agent_clears_requiere_humano(env) -> None:
    client, _, ids = env
    paused = client.patch(f"/api/inbox/contacts/{ids['luis']}", json={"bot_paused": True}).json()
    assert paused["bot_paused"] is True
    resumed = client.patch(f"/api/inbox/contacts/{ids['luis']}", json={"bot_paused": False}).json()
    assert resumed["bot_paused"] is False
    assert resumed["status"] == "en_conversacion"
    assert client.patch(f"/api/inbox/contacts/{ids['luis']}", json={"status": "x"}).status_code == 422


def test_manual_reply_sends_and_pauses_agent(env, monkeypatch: pytest.MonkeyPatch) -> None:
    client, Session, ids = env
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(dm_sender, "send_text", lambda tok, rid, text, **k: sent.append((rid, text)) or "mid-out")
    resp = client.post(f"/api/inbox/contacts/{ids['ana']}/reply", json={"text": "Hola Ana, te llamo hoy"})
    assert resp.status_code == 200
    assert resp.json()["bot_paused"] is True
    assert sent == [("s1", "Hola Ana, te llamo hoy")]
    with Session() as s:
        out = s.execute(select(DmMessage).where(DmMessage.direction == "out")).scalar_one()
        assert out.sent_by == "human"


def test_manual_reply_outside_24h_window_is_rejected(env, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, ids = env
    monkeypatch.setattr(dm_sender, "send_text", lambda *a, **k: pytest.fail("no debe enviar"))
    assert client.post(f"/api/inbox/contacts/{ids['luis']}/reply", json={"text": "Hola"}).status_code == 409


def test_toggle_agent_subscribes_page(env, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, ids = env
    calls: list[str] = []
    monkeypatch.setattr(dm_sender, "subscribe_page_to_messages", lambda page_id, tok, **k: calls.append(page_id) or True)
    resp = client.patch(f"/api/inbox/accounts/{ids['acc']}", json={"dm_agent_enabled": True}).json()
    assert resp == {"id": ids["acc"], "dm_agent_enabled": True, "webhook_subscribed": True}
    assert calls == ["page-a"]
    accounts = client.get("/api/inbox/accounts").json()["items"]
    assert [(a["id"], a["dm_agent_enabled"], a["contacts"]) for a in accounts] == [(ids["acc"], True, 2)]
    assert client.patch(f"/api/inbox/accounts/{ids['other']}", json={"dm_agent_enabled": True}).status_code == 404


def test_csv_export(env) -> None:
    client, _, _ = env
    resp = client.get("/api/inbox/contacts.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    body = resp.content.decode("utf-8")
    assert body.startswith("\ufeffNombre,Perfil,Teléfono")
    assert "Ana Pérez" in body and "Otro Tenant" not in body
