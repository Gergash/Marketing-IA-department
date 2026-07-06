"""Pruebas de /api/runs/sync y /api/runs/async: rechazo 422 de reel en sync, ruteo reel en async."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gateway.app.api.routes import run_pipeline_async, run_pipeline_sync
from gateway.app.db.session import Base
from gateway.app.models import Brief
from gateway.app.schemas.contracts import RunRequest


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """BD SQLite aislada con mock image + LLM stub (sin GPU, Ollama ni API keys)."""
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("SOCIAL_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path / 'runs_api_test.db'}")
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
        tema="reel test",
        publico_objetivo="audiencia objetivo",
        red_social="instagram",
        objetivo="branding",
    )
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


def test_sync_rejects_reel_with_422(db_session, brief) -> None:
    payload = RunRequest(brief_id=brief.id, content_format="reel")
    with pytest.raises(HTTPException) as exc_info:
        run_pipeline_sync(payload, tenant_id="demo-tenant", db=db_session)
    assert exc_info.value.status_code == 422


def test_sync_still_accepts_feed(db_session, brief) -> None:
    payload = RunRequest(brief_id=brief.id, content_format="feed", publish=False, requires_approval=True)
    response = run_pipeline_sync(payload, tenant_id="demo-tenant", db=db_session)
    assert response.status == "pending_approval"


def test_async_routes_reel_to_video_task(monkeypatch: pytest.MonkeyPatch, db_session, brief) -> None:
    from workers import tasks as tasks_module

    captured: dict = {}

    def _fake_apply_async(*, args, kwargs, **extra):
        captured["args"] = args
        captured["kwargs"] = kwargs
        captured["extra"] = extra

    monkeypatch.setattr(tasks_module.execute_video_pipeline_task, "apply_async", _fake_apply_async)

    payload = RunRequest(brief_id=brief.id, content_format="reel")
    response = run_pipeline_async(payload, tenant_id="demo-tenant", db=db_session)

    assert response.status == "queued"
    assert captured["extra"].get("queue") == "video_render"


def test_sync_rejects_user_clip_reel_with_422(db_session, brief) -> None:
    payload = RunRequest(brief_id=brief.id, content_format="user_clip_reel", drive_folder_id="folder123")
    with pytest.raises(HTTPException) as exc_info:
        run_pipeline_sync(payload, tenant_id="demo-tenant", db=db_session)
    assert exc_info.value.status_code == 422


def test_async_routes_user_clip_reel_to_video_task(monkeypatch: pytest.MonkeyPatch, db_session, brief) -> None:
    from workers import tasks as tasks_module

    captured: dict = {}

    def _fake_apply_async(*, args, kwargs, **extra):
        captured["args"] = args
        captured["kwargs"] = kwargs
        captured["extra"] = extra

    monkeypatch.setattr(tasks_module.execute_video_pipeline_task, "apply_async", _fake_apply_async)

    payload = RunRequest(brief_id=brief.id, content_format="user_clip_reel", drive_folder_id="folder123")
    response = run_pipeline_async(payload, tenant_id="demo-tenant", db=db_session)

    assert response.status == "queued"
    assert captured["extra"].get("queue") == "video_render"
    assert captured["kwargs"]["drive_folder_id"] == "folder123"


def test_execute_pipeline_user_clip_reel_reaches_pending_approval(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    """Async run accepted (spec): user_clip_reel llega a pending_approval via el mismo HITL existente."""
    from agents.marketing_agents.clip_reel_designer import ClipReelDesigner
    from agents.marketing_agents.schemas import VideoDesignOutput
    from gateway.app.services.pipeline_service import create_run, execute_pipeline

    captured_kwargs: dict = {}

    def _fake_run(self, brief_in, copy, strategy, **kwargs):
        captured_kwargs.update(kwargs)
        return VideoDesignOutput(
            image_url=None,
            video_url="http://localhost:8000/static/videos/clipreel.mp4",
            video_prompt=strategy.hook,
            video_provider="mock",
            voice_provider="",
            width=1080,
            height=1920,
            duration_s=20.0,
            scene_count=1,
            layout_archetype="typographic_poster",
        )

    monkeypatch.setattr(ClipReelDesigner, "run", _fake_run)

    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="async",
        idempotency_key=None,
        content_format="user_clip_reel",
    )
    result = execute_pipeline(
        db_session,
        run.id,
        publish=True,
        requires_approval=True,
        idempotency_key=None,
        drive_folder_id="folder123",
    )

    assert result["design"]["video_url"] == "http://localhost:8000/static/videos/clipreel.mp4"
    assert captured_kwargs["drive_folder_id"] == "folder123"
    db_session.refresh(run)
    assert run.status == "pending_approval"


def test_async_routes_feed_to_default_task_without_video_queue(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    from workers import tasks as tasks_module

    captured: dict = {}

    def _fake_apply_async(*, args, kwargs, **extra):
        captured["args"] = args
        captured["kwargs"] = kwargs
        captured["extra"] = extra

    monkeypatch.setattr(tasks_module.execute_pipeline_task, "apply_async", _fake_apply_async)

    payload = RunRequest(brief_id=brief.id, content_format="feed")
    response = run_pipeline_async(payload, tenant_id="demo-tenant", db=db_session)

    assert response.status == "queued"
    assert "queue" not in captured["extra"]
