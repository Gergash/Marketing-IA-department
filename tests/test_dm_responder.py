"""Agente de DMs: salida del LLM, aviso de privacidad, fusión de datos y reglas del turno (pausa, debounce, fallo LLM)."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from agents.marketing_agents import dm_responder, dm_sender
from agents.marketing_agents.dm_responder import DmResponderAgent
from gateway.app.db.session import Base
from gateway.app.models import DmContact, DmMessage, OAuthToken
from gateway.app.services import dm_service

PRIVACY = "https://example.test/privacidad"


class FakeLLM:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.response


def _run(llm, contact=None, history=None):
    return DmResponderAgent(llm=llm).run(
        history or [{"role": "persona", "text": "Hola, ¿tienen apartamentos en arriendo?"}],
        contact or {},
        brand_name="Marca Test",
        privacy_url=PRIVACY,
    )


def test_llm_failures_return_llm_error() -> None:
    assert _run(FakeLLM(error=RuntimeError("429")))["llm_error"] is True
    assert _run(FakeLLM(response={"reply": "  "}))["llm_error"] is True
    assert _run(FakeLLM(response=["no", "es", "dict"]))["llm_error"] is True


def test_no_llm_configured_returns_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dm_responder, "get_llm", lambda: None)
    assert DmResponderAgent().run([], {}, brand_name="X")["llm_error"] is True


def test_privacy_notice_appended_first_time_data_is_requested() -> None:
    llm = FakeLLM(response={
        "reply": "¡Claro que sí! ¿Cómo te llamas?",
        "motive": "Busca apartamento en arriendo",
        "motive_category": "informacion",
        "asked_for_personal_data": True,
        "needs_human": False,
    })
    out = _run(llm)
    assert PRIVACY in out["reply"]
    assert out["privacy_notice_included"] is True
    assert out["motive"] == "Busca apartamento en arriendo"
    assert "Marca Test" in llm.calls[0][0]


def test_privacy_notice_not_repeated() -> None:
    llm = FakeLLM(response={"reply": "¿Y tu número de WhatsApp?", "asked_for_personal_data": True})
    out = _run(llm, contact={"privacy_notice_sent": True})
    assert PRIVACY not in out["reply"]
    assert out["privacy_notice_included"] is False


def test_long_reply_truncated_without_cutting_privacy_link() -> None:
    llm = FakeLLM(response={"reply": "a" * 2000, "asked_for_personal_data": True})
    out = _run(llm)
    assert len(out["reply"]) <= 900
    assert out["reply"].endswith(PRIVACY)


def test_merge_does_not_overwrite_with_nulls_and_sets_status() -> None:
    contact = DmContact(full_name="Ana Pérez", phone=None, city=None, status="nuevo")
    dm_service.merge_agent_result(contact, {"full_name": None, "phone": "3001234567", "motive_category": "RARO"})
    assert contact.full_name == "Ana Pérez"
    assert contact.phone == "3001234567"
    assert contact.motive_category == "otro"
    assert contact.status == "en_conversacion"

    dm_service.merge_agent_result(contact, {"city": "Laureles, Medellín", "full_name": "null"})
    assert contact.full_name == "Ana Pérez"
    assert contact.status == "datos_completos"

    dm_service.merge_agent_result(contact, {"needs_human": True})
    assert contact.status == "requiere_humano"


# ---------------------------------------------------------------------------
# handle_agent_turn
# ---------------------------------------------------------------------------

@pytest.fixture
def turn_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DM_AGENT_REPLY_DELAY_SECONDS", "0")
    monkeypatch.setattr(dm_service, "_brand_context", lambda tenant_id: "")
    engine = create_engine(f"sqlite:///{tmp_path / 'dm_turn_test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()

    account = OAuthToken(
        tenant_id="t1", provider="meta", access_token="page-token",
        account_id="ig-1", account_name="marca", page_id="page-1", dm_agent_enabled=True,
    )
    session.add(account)
    session.flush()
    contact = DmContact(
        tenant_id="t1", oauth_token_id=account.id, platform="instagram", sender_id="igsid-1",
        display_name="Ana", status="nuevo",
    )
    session.add(contact)
    session.flush()
    msg = DmMessage(contact_id=contact.id, direction="in", sent_by="contact", text="Hola", meta_mid="m1",
                    created_at=datetime.utcnow())
    session.add(msg)
    session.commit()

    sent: list[str] = []
    monkeypatch.setattr(dm_sender, "send_typing", lambda *a, **k: None)
    monkeypatch.setattr(dm_sender, "fetch_profile_name", lambda *a, **k: "Ana")
    monkeypatch.setattr(dm_sender, "send_text", lambda token, rid, text, **k: sent.append(text) or f"out-{len(sent)}")

    def use_agent(result: dict) -> None:
        class StubAgent:
            def run(self, *args, **kwargs):
                return result
        monkeypatch.setattr(dm_responder, "DmResponderAgent", StubAgent)

    try:
        yield session, account, contact, msg, sent, use_agent
    finally:
        session.close()


def test_turn_replies_and_merges_data(turn_env) -> None:
    session, _, contact, msg, sent, use_agent = turn_env
    use_agent({"reply": "¡Hola Ana! ¿En qué te ayudo?", "motive": "Info general", "motive_category": "informacion",
               "needs_human": False, "privacy_notice_included": False})
    assert dm_service.handle_agent_turn(session, contact.id, msg.id) == "replied"
    assert sent == ["¡Hola Ana! ¿En qué te ayudo?"]
    session.refresh(contact)
    assert contact.status == "en_conversacion"
    assert contact.motive == "Info general"
    out = session.execute(select(DmMessage).where(DmMessage.direction == "out")).scalar_one()
    assert out.sent_by == "agent"


def test_turn_dry_run_stores_reply_without_calling_meta(turn_env, monkeypatch: pytest.MonkeyPatch) -> None:
    session, _, contact, msg, sent, use_agent = turn_env
    monkeypatch.setenv("DM_AGENT_DRY_RUN", "true")
    use_agent({"reply": "¡Hola! ¿Cómo te llamas?", "needs_human": False})
    assert dm_service.handle_agent_turn(session, contact.id, msg.id) == "replied"
    assert sent == []
    out = session.execute(select(DmMessage).where(DmMessage.direction == "out")).scalar_one()
    assert out.text == "¡Hola! ¿Cómo te llamas?" and out.meta_mid is None


def test_turn_llm_error_hands_off_without_sending(turn_env) -> None:
    session, _, contact, msg, sent, use_agent = turn_env
    use_agent({"llm_error": True})
    assert dm_service.handle_agent_turn(session, contact.id, msg.id) == "llm_error"
    assert sent == []
    session.refresh(contact)
    assert contact.status == "requiere_humano"


def test_turn_skips_when_paused_disabled_or_human(turn_env) -> None:
    session, account, contact, msg, sent, use_agent = turn_env
    use_agent({"reply": "no debería salir"})

    contact.bot_paused = True
    session.commit()
    assert dm_service.handle_agent_turn(session, contact.id, msg.id) == "bot_paused"

    contact.bot_paused = False
    contact.status = "requiere_humano"
    session.commit()
    assert dm_service.handle_agent_turn(session, contact.id, msg.id) == "status_requiere_humano"

    contact.status = "en_conversacion"
    account.dm_agent_enabled = False
    session.commit()
    assert dm_service.handle_agent_turn(session, contact.id, msg.id) == "agent_disabled"
    assert sent == []


def test_turn_debounced_when_newer_message_exists(turn_env) -> None:
    session, _, contact, msg, sent, use_agent = turn_env
    use_agent({"reply": "hola"})
    session.add(DmMessage(contact_id=contact.id, direction="in", sent_by="contact", text="¿sigues?", meta_mid="m2",
                          created_at=datetime.utcnow()))
    session.commit()
    assert dm_service.handle_agent_turn(session, contact.id, msg.id) == "debounced"
    assert sent == []
