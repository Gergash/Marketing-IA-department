"""Pruebas del disparo programado: pipeline en pending_approval sin publicación."""

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gateway.app.db.session import Base
from gateway.app.models import AgentRun, Brief, Publication
from gateway.app.services.pipeline_service import create_run, execute_pipeline


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """BD SQLite aislada con mock image + LLM stub (sin GPU, Ollama ni API keys)."""
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path / 'scheduler_test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_scheduled_pipeline_ends_pending_approval_without_publish(db_session) -> None:
    """Replica _fire_campaign: requires_approval=True → pending_approval, sin publicación."""
    brief = Brief(
        tenant_id="demo-tenant",
        tema="Prueba de Fuego Scheduler",
        publico_objetivo="audiencia objetivo de la marca",
        red_social="instagram",
        objetivo="branding",
    )
    db_session.add(brief)
    db_session.commit()
    db_session.refresh(brief)

    idem_key = "campaign-1-test"
    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="scheduled",
        idempotency_key=idem_key,
    )

    result = execute_pipeline(
        db_session,
        run.id,
        publish=False,
        requires_approval=True,
        idempotency_key=idem_key,
    )

    db_session.refresh(run)
    assert run.status == "pending_approval"
    assert run.result_json is not None
    assert result["publish_result"] is None
    assert "copy" in result
    assert "design" in result

    parsed = json.loads(run.result_json)
    assert parsed.get("publish_result") is None

    pubs = list(db_session.execute(select(Publication)).scalars().all())
    assert pubs == []


def test_scheduled_run_has_run_mode_scheduled(db_session) -> None:
    """Los runs del scheduler deben marcarse con run_mode=scheduled."""
    brief = Brief(
        tenant_id="demo-tenant",
        tema="cron test",
        publico_objetivo="test",
        red_social="instagram",
        objetivo="branding",
    )
    db_session.add(brief)
    db_session.commit()

    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="scheduled",
        idempotency_key="idem-scheduled",
    )
    assert run.run_mode == "scheduled"
    assert run.status == "queued"
