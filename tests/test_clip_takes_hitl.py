"""Pruebas del HITL de tomas: pending_takes, update_run_takes, render_takes_for_run."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.marketing_agents.schemas import TakeProposal, VideoDesignOutput
from gateway.app.db.session import Base
from gateway.app.models import Brief
from gateway.app.services.pipeline_service import (
    create_run,
    execute_pipeline,
    get_run_takes,
    render_takes_for_run,
    update_run_takes,
)


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("SOCIAL_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("VIDEO_PROVIDER", "mock")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path / 'takes_hitl_test.db'}")
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
        tema="clip takes test",
        publico_objetivo="audiencia objetivo",
        red_social="instagram",
        objetivo="branding",
        tono_marca="profesional",
        idioma="es",
    )
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


def _fake_propose_output(strategy_hook: str = "hook") -> VideoDesignOutput:
    return VideoDesignOutput(
        image_url=None,
        video_url="",
        video_prompt=strategy_hook,
        video_provider="mock",
        voice_provider="",
        width=0,
        height=0,
        duration_s=20.0,
        scene_count=2,
        layout_archetype="typographic_poster",
        takes=[
            TakeProposal(
                id="take-1",
                clip_id="clip1",
                source_clip_url="http://localhost/static/c1.mp4",
                trim_in=0.0,
                trim_out=12.0,
                duration_s=12.0,
                transcript="primer momento",
                is_hook=True,
                status="proposed",
                order=0,
            ),
            TakeProposal(
                id="take-2",
                clip_id="clip1",
                source_clip_url="http://localhost/static/c1.mp4",
                trim_in=12.0,
                trim_out=20.0,
                duration_s=8.0,
                transcript="segundo momento",
                status="proposed",
                order=1,
            ),
        ],
    )


def test_execute_pipeline_user_clip_reel_reaches_pending_takes(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    from agents.marketing_agents.clip_reel_designer import ClipReelDesigner

    def _fake_run(self, brief_in, copy, strategy, **kwargs):
        return _fake_propose_output(strategy.hook)

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

    assert result["design"]["video_url"] == ""
    assert len(result["design"]["takes"]) == 2
    db_session.refresh(run)
    assert run.status == "pending_takes"


def test_update_run_takes_requires_accepted_in_band(db_session, brief) -> None:
    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="async",
        idempotency_key=None,
        content_format="user_clip_reel",
    )
    design = _fake_propose_output().model_dump()
    run.status = "pending_takes"
    run.result_json = json.dumps(
        {
            "strategy": {"hook": "hook"},
            "copy": {},
            "design": design,
            "quality": {"approved": True},
        },
        ensure_ascii=True,
    )
    db_session.add(run)
    db_session.commit()

    # Sin accepted: permite guardar (p. ej. trim) sin error
    takes = update_run_takes(
        db_session,
        run.id,
        [{"id": "take-1", "status": "proposed"}, {"id": "take-2", "status": "proposed"}],
    )
    assert takes[0]["status"] == "proposed"

    takes = update_run_takes(
        db_session,
        run.id,
        [{"id": "take-1", "status": "accepted"}, {"id": "take-2", "status": "rejected"}],
    )
    assert takes[0]["status"] == "accepted"
    assert takes[1]["status"] == "rejected"
    assert get_run_takes(db_session, run.id)[0]["status"] == "accepted"


def test_render_takes_for_run_goes_pending_approval(monkeypatch: pytest.MonkeyPatch, db_session, brief) -> None:
    from agents.marketing_agents.clip_reel_designer import ClipReelDesigner

    def _fake_render(self, takes, *, strategy_hook, video_provider=None, **kwargs):
        return VideoDesignOutput(
            video_url="http://localhost/static/final.mp4",
            video_prompt=strategy_hook,
            video_provider="mock",
            width=1080,
            height=1920,
            duration_s=12.0,
            scene_count=1,
            takes=takes,
        )

    monkeypatch.setattr(ClipReelDesigner, "render_from_takes", _fake_render)

    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="async",
        idempotency_key=None,
        content_format="user_clip_reel",
    )
    design = _fake_propose_output().model_dump()
    design["takes"][0]["status"] = "accepted"
    design["takes"][1]["status"] = "rejected"
    run.status = "pending_takes"
    run.result_json = json.dumps(
        {
            "strategy": {"hook": "hook de prueba"},
            "copy": {},
            "design": design,
            "quality": {"approved": True},
        },
        ensure_ascii=True,
    )
    db_session.add(run)
    db_session.commit()

    result = render_takes_for_run(db_session, run.id)
    db_session.refresh(run)
    assert run.status == "pending_approval"
    assert result["design"]["video_url"] == "http://localhost/static/final.mp4"
    assert result["design"]["takes"][0]["status"] == "accepted"
