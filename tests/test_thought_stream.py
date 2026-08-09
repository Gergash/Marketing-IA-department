"""Pruebas del hilo de pensamiento: narración de agentes y participación del usuario."""

import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.marketing_agents import thought_stream
from agents.marketing_agents.thought_stream import (
    CHECKPOINT_COPY,
    CHECKPOINT_DESIGN,
    CHECKPOINT_STRATEGY,
    NullThoughtStream,
    RunCancelledByUser,
    ThoughtStream,
    build_stream,
    push_reply,
    read_events,
)
from gateway.app.api.routes import get_thoughts, reply_to_thought, run_pipeline_sync
from gateway.app.db.session import Base
from gateway.app.models import Brief
from gateway.app.schemas.contracts import RunRequest, ThoughtReplyRequest


@pytest.fixture(autouse=True)
def memory_backend():
    """Aísla cada test en un transporte en memoria (sin depender de Redis)."""
    thought_stream.reset_backend(thought_stream._MemoryBackend())
    yield
    thought_stream.reset_backend(None)


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """BD SQLite aislada con mock image + LLM stub (sin GPU, Ollama ni API keys)."""
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("SOCIAL_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path / 'thoughts_test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def brief(db_session):
    b = Brief(
        tenant_id="demo-tenant",
        tema="hilo de pensamiento",
        publico_objetivo="dueños de negocio",
        red_social="instagram",
        objetivo="branding",
    )
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


# ---------------------------------------------------------------------------
# Stream aislado
# ---------------------------------------------------------------------------

def test_events_are_readable_with_cursor() -> None:
    stream = ThoughtStream("t-cursor")
    stream.think("strategist", "pensando")
    stream.output("strategist", "listo", hook="hola")

    events = read_events("t-cursor")
    assert [e["phase"] for e in events] == ["thinking", "output"]
    assert events[0]["agent_label"] == "Estratega de contenido"
    assert events[1]["data"]["hook"] == "hola"
    # El cursor avanza: un segundo poll solo trae lo nuevo.
    assert read_events("t-cursor", 2) == []


def test_ask_returns_continue_without_interactive_mode() -> None:
    stream = ThoughtStream("t-auto", interactive=False)
    decision = stream.ask("strategist", CHECKPOINT_STRATEGY, "¿seguimos?")

    assert decision == {"action": "continue", "notes": "", "source": "auto"}
    # Sin modo interactivo no se molesta al usuario con preguntas.
    assert read_events("t-auto") == []


def test_ask_blocks_until_user_answers() -> None:
    stream = ThoughtStream("t-ask", interactive=True, checkpoint_timeout_s=5)
    threading.Timer(
        0.1, lambda: push_reply("t-ask", action="adjust", notes="más corto", checkpoint=CHECKPOINT_COPY)
    ).start()

    decision = stream.ask("copywriter", CHECKPOINT_COPY, "¿te sirve?")

    assert decision["action"] == "adjust"
    assert decision["notes"] == "más corto"
    assert decision["source"] == "user"
    phases = [e["phase"] for e in read_events("t-ask")]
    assert phases == ["question", "answer"]


def test_ask_continues_alone_when_nobody_answers() -> None:
    stream = ThoughtStream("t-timeout", interactive=True, checkpoint_timeout_s=0.2)

    decision = stream.ask("designer", CHECKPOINT_DESIGN, "¿indicaciones de arte?")

    assert decision == {"action": "continue", "notes": "", "source": "timeout"}
    assert read_events("t-timeout")[-1]["data"]["source"] == "timeout"


def test_ask_ignores_reply_from_another_checkpoint() -> None:
    stream = ThoughtStream("t-stale", interactive=True, checkpoint_timeout_s=1)
    push_reply("t-stale", action="adjust", notes="tarde", checkpoint=CHECKPOINT_STRATEGY)

    decision = stream.ask("copywriter", CHECKPOINT_COPY, "¿te sirve?")

    assert decision["source"] == "timeout"


def test_adjust_without_notes_degrades_to_continue() -> None:
    stream = ThoughtStream("t-empty", interactive=True, checkpoint_timeout_s=2)
    threading.Timer(0.1, lambda: push_reply("t-empty", action="adjust", notes="   ")).start()

    assert stream.ask("copywriter", CHECKPOINT_COPY, "¿?")["action"] == "continue"


def test_cancel_stops_the_run() -> None:
    stream = ThoughtStream("t-cancel", interactive=True, checkpoint_timeout_s=2)
    threading.Timer(0.1, lambda: push_reply("t-cancel", action="cancel")).start()

    with pytest.raises(RunCancelledByUser) as exc_info:
        stream.ask("strategist", CHECKPOINT_STRATEGY, "¿seguimos?")

    assert exc_info.value.checkpoint == CHECKPOINT_STRATEGY


def test_push_reply_rejects_unknown_action() -> None:
    with pytest.raises(ValueError):
        push_reply("t-bad", action="explota")


def test_build_stream_without_trace_id_is_null() -> None:
    assert isinstance(build_stream(None), NullThoughtStream)
    assert isinstance(build_stream(""), NullThoughtStream)


def test_build_stream_is_null_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THOUGHTS_ENABLED", "false")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()
    assert isinstance(build_stream("t-off"), NullThoughtStream)


# ---------------------------------------------------------------------------
# Integración con el pipeline y la API
# ---------------------------------------------------------------------------

def test_sync_run_narrates_every_agent(db_session, brief) -> None:
    payload = RunRequest(
        brief_id=brief.id,
        content_format="feed",
        publish=False,
        requires_approval=True,
        trace_id="t-run",
    )
    run_pipeline_sync(payload, tenant_id="demo-tenant", db=db_session)

    events = read_events("t-run")
    agents = [e["agent"] for e in events]
    assert agents[0] == "pipeline"
    assert events[0]["phase"] == "start"
    assert {"strategist", "copywriter", "qa", "designer"} <= set(agents)
    assert events[-1]["phase"] == "end"
    # Sin modo interactivo, el run nunca se detiene a preguntar.
    assert not any(e["phase"] == "question" for e in events)


def test_sync_run_without_trace_id_emits_nothing(db_session, brief) -> None:
    payload = RunRequest(brief_id=brief.id, content_format="feed", publish=False, requires_approval=True)
    run_pipeline_sync(payload, tenant_id="demo-tenant", db=db_session)

    assert read_events("") == []


def test_interactive_run_waits_and_applies_user_notes(db_session, brief, monkeypatch) -> None:
    monkeypatch.setenv("THOUGHTS_CHECKPOINT_TIMEOUT_SECONDS", "5")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    payload = RunRequest(
        brief_id=brief.id,
        content_format="feed",
        publish=False,
        requires_approval=True,
        trace_id="t-interactive",
        interactive=True,
    )

    # El usuario contesta a los tres checkpoints: ajusta el copy y deja pasar el resto.
    answers = [
        {"action": "continue", "checkpoint": CHECKPOINT_STRATEGY},
        {"action": "adjust", "notes": "menos técnico", "checkpoint": CHECKPOINT_COPY},
        {"action": "continue", "checkpoint": CHECKPOINT_COPY},
        {"action": "continue", "checkpoint": CHECKPOINT_DESIGN},
    ]

    def answer_when_asked() -> None:
        """Responde en cuanto aparece cada pregunta, como haría el dashboard."""
        seen = 0
        import time

        deadline = time.monotonic() + 20
        for reply in answers:
            while time.monotonic() < deadline:
                questions = [e for e in read_events("t-interactive") if e["phase"] == "question"]
                if len(questions) > seen:
                    seen = len(questions)
                    break
                time.sleep(0.05)
            push_reply("t-interactive", **{"action": "continue", "notes": "", **reply})

    responder = threading.Thread(target=answer_when_asked, daemon=True)
    responder.start()
    response = run_pipeline_sync(payload, tenant_id="demo-tenant", db=db_session)
    responder.join(timeout=5)

    assert response.status == "pending_approval"
    events = read_events("t-interactive")
    checkpoints = [e["checkpoint"] for e in events if e["phase"] == "question"]
    assert checkpoints == [CHECKPOINT_STRATEGY, CHECKPOINT_COPY, CHECKPOINT_COPY, CHECKPOINT_DESIGN]
    # El copy se reescribió tras el ajuste: hay dos vueltas del copywriter por petición del usuario.
    copy_rounds = [e for e in events if e["agent"] == "copywriter" and e["phase"] == "output"]
    assert len(copy_rounds) >= 2


def test_interactive_cancel_leaves_run_rejected(db_session, brief, monkeypatch) -> None:
    monkeypatch.setenv("THOUGHTS_CHECKPOINT_TIMEOUT_SECONDS", "5")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    payload = RunRequest(
        brief_id=brief.id,
        content_format="feed",
        publish=False,
        requires_approval=True,
        trace_id="t-stop",
        interactive=True,
    )
    threading.Timer(0.3, lambda: push_reply("t-stop", action="cancel")).start()

    response = run_pipeline_sync(payload, tenant_id="demo-tenant", db=db_session)

    assert response.status == "rejected"
    assert response.result is None


def test_thoughts_endpoints_expose_events_and_accept_replies() -> None:
    ThoughtStream("t-api").think("designer", "componiendo")

    page = get_thoughts("t-api", since=0, tenant_id="demo-tenant")
    assert page.next_since == 1
    assert page.events[0].agent == "designer"
    assert get_thoughts("t-api", since=page.next_since, tenant_id="demo-tenant").events == []

    reply = reply_to_thought(
        "t-api",
        ThoughtReplyRequest(action="adjust", notes="fondo más oscuro", checkpoint=CHECKPOINT_DESIGN),
        tenant_id="demo-tenant",
    )
    assert reply.accepted is True
    assert thought_stream.get_backend().pop_reply("t-api", 1)["notes"] == "fondo más oscuro"


def test_reply_request_requires_notes_when_adjusting() -> None:
    with pytest.raises(ValueError):
        ThoughtReplyRequest(action="adjust", notes="   ")
