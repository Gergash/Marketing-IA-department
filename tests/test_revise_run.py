"""Pruebas de POST /api/runs/{id}/revise: persistencia de params, re-ejecucion con notas y ruteo de video."""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gateway.app.db.session import Base
from gateway.app.models import AgentRun, Brief


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """BD SQLite aislada con mock image + LLM stub (sin GPU, Ollama ni API keys)."""
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("SOCIAL_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path / 'revise_test.db'}")
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
        tema="revise test",
        publico_objetivo="audiencia objetivo",
        red_social="instagram",
        objetivo="branding",
    )
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


def _pending_run(db_session, brief, *, content_format="feed", params=None):
    """Crea un run ya en pending_approval con params persistidos, como lo dejaria execute_pipeline."""
    from gateway.app.services.pipeline_service import create_run

    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="sync",
        idempotency_key=None,
        content_format=content_format,
        params=params or {},
    )
    run.status = "pending_approval"
    run.result_json = json.dumps({"quality": {"approved": True}})
    db_session.commit()
    db_session.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Persistencia de parametros del run original
# ---------------------------------------------------------------------------


def test_create_run_persists_params(db_session, brief) -> None:
    """Sin params guardados no se puede re-ejecutar fielmente: create_run debe serializarlos."""
    from gateway.app.services.pipeline_service import create_run

    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="sync",
        idempotency_key=None,
        content_format="feed",
        params={"archetype_override": "cinematic_hero", "image_provider": "fal"},
    )

    stored = json.loads(run.run_params_json)
    assert stored["archetype_override"] == "cinematic_hero"
    assert stored["image_provider"] == "fal"


def test_create_run_without_params_is_empty_dict(db_session, brief) -> None:
    from gateway.app.services.pipeline_service import create_run

    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="sync",
        idempotency_key=None,
        content_format="feed",
    )
    assert json.loads(run.run_params_json) == {}


# ---------------------------------------------------------------------------
# revise_run: validaciones de estado
# ---------------------------------------------------------------------------


def test_revise_rejects_run_not_pending_approval(db_session, brief) -> None:
    from gateway.app.services.pipeline_service import create_run, revise_run

    run = create_run(
        db_session,
        brief_id=brief.id,
        tenant_id="demo-tenant",
        run_mode="sync",
        idempotency_key=None,
        content_format="feed",
    )
    run.status = "completed"
    db_session.commit()

    with pytest.raises(ValueError, match="pending_approval"):
        revise_run(db_session, run.id, notes="mas contraste")


def test_revise_rejects_unknown_run(db_session) -> None:
    from gateway.app.services.pipeline_service import revise_run

    with pytest.raises(ValueError, match="not found"):
        revise_run(db_session, 999999, notes="mas contraste")


# ---------------------------------------------------------------------------
# revise_run: re-ejecucion con notas
# ---------------------------------------------------------------------------


def test_revise_reruns_designer_with_notes_and_stays_pending(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    from agents.marketing_agents.designer import DesignerAgent
    from agents.marketing_agents.schemas import DesignOutput
    from gateway.app.services.pipeline_service import revise_run

    captured: dict = {}

    def _fake_run(self, brief_in, copy, strategy, **kwargs):
        captured.update(kwargs)
        return DesignOutput(
            image_url="http://localhost:8000/static/images/revised.png",
            image_prompt="p",
            image_provider="mock",
            image_width=1080,
            image_height=1350,
            content_format="feed",
            layout_archetype="typographic_poster",
            layout_label="Poster",
            color_palette="",
            design_source="generated",
        )

    monkeypatch.setattr(DesignerAgent, "run", _fake_run)

    run = _pending_run(db_session, brief)
    result = revise_run(db_session, run.id, notes="mas contraste y menos texto")

    assert captured["revision_notes"] == "mas contraste y menos texto"
    assert result["design"]["image_url"].endswith("revised.png")

    db_session.refresh(run)
    assert run.status == "pending_approval"
    assert run.revision_count == 1
    assert "mas contraste" in run.revision_notes


def test_revise_preserves_original_run_params(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    """La re-ejecucion debe respetar arquetipo/foto/proveedor del run original, no los defaults."""
    from agents.marketing_agents.designer import DesignerAgent
    from agents.marketing_agents.schemas import DesignOutput
    from gateway.app.services.pipeline_service import revise_run

    captured: dict = {}

    def _fake_run(self, brief_in, copy, strategy, **kwargs):
        captured.update(kwargs)
        return DesignOutput(
            image_url="http://localhost:8000/static/images/revised.png",
            image_prompt="p",
            image_provider="mock",
            image_width=1080,
            image_height=1350,
            content_format="feed",
            layout_archetype="cinematic_hero",
            layout_label="Hero",
            color_palette="",
            design_source="user_overlay",
        )

    monkeypatch.setattr(DesignerAgent, "run", _fake_run)

    run = _pending_run(
        db_session,
        brief,
        params={
            "archetype_override": "cinematic_hero",
            "user_asset_url": "http://localhost:8000/static/uploads/foto.jpg",
            "image_provider": "fal",
            "alter_image_with_ai": True,
            "visual_instructions": "fondo azul",
        },
    )
    revise_run(db_session, run.id, notes="subir el logo")

    assert captured["archetype_override"] == "cinematic_hero"
    assert captured["user_asset_url"] == "http://localhost:8000/static/uploads/foto.jpg"
    assert captured["alter_image_with_ai"] is True
    assert captured["visual_instructions"] == "fondo azul"


def test_revise_accumulates_notes_across_revisions(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    from agents.marketing_agents.designer import DesignerAgent
    from agents.marketing_agents.schemas import DesignOutput
    from gateway.app.services.pipeline_service import revise_run

    def _fake_run(self, brief_in, copy, strategy, **kwargs):
        return DesignOutput(
            image_url="http://localhost:8000/static/images/r.png",
            image_prompt="p",
            image_provider="mock",
            image_width=1080,
            image_height=1350,
            content_format="feed",
            layout_archetype="typographic_poster",
            layout_label="Poster",
            color_palette="",
            design_source="generated",
        )

    monkeypatch.setattr(DesignerAgent, "run", _fake_run)

    run = _pending_run(db_session, brief)
    revise_run(db_session, run.id, notes="primera nota")
    db_session.refresh(run)
    assert run.revision_count == 1

    revise_run(db_session, run.id, notes="segunda nota")
    db_session.refresh(run)
    assert run.revision_count == 2
    assert "primera nota" in run.revision_notes
    assert "segunda nota" in run.revision_notes


# ---------------------------------------------------------------------------
# Pipeline: propagacion de revision_notes a cada branch
# ---------------------------------------------------------------------------


def test_pipeline_forwards_revision_notes_to_video_designer(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents.pipeline import MarketingPipeline
    from agents.marketing_agents.schemas import BriefInput, VideoDesignOutput
    from agents.marketing_agents.video_designer import VideoDesignerAgent

    captured: dict = {}

    def _fake_run(self, brief_in, copy, strategy, **kwargs):
        captured.update(kwargs)
        return VideoDesignOutput(
            image_url=None,
            video_url="http://localhost:8000/static/videos/r.mp4",
            video_prompt="h",
            video_provider="mock",
            voice_provider="",
            width=1080,
            height=1920,
            duration_s=20.0,
            scene_count=3,
            layout_archetype="cinematic_hero",
        )

    monkeypatch.setattr(VideoDesignerAgent, "run", _fake_run)

    pipeline = MarketingPipeline()
    pipeline.run(
        BriefInput(
            tema="tema",
            publico_objetivo="audiencia",
            red_social="instagram",
            objetivo="branding",
        ),
        publish=False,
        content_format="reel",
        revision_notes="acortar el hook",
    )

    assert captured["revision_notes"] == "acortar el hook"


def test_pipeline_forwards_revision_notes_to_clip_reel_designer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agents.marketing_agents.clip_reel_designer import ClipReelDesigner
    from agents.marketing_agents.pipeline import MarketingPipeline
    from agents.marketing_agents.schemas import BriefInput, VideoDesignOutput

    captured: dict = {}

    def _fake_run(self, brief_in, copy, strategy, **kwargs):
        captured.update(kwargs)
        return VideoDesignOutput(
            image_url=None,
            video_url="http://localhost:8000/static/videos/c.mp4",
            video_prompt="h",
            video_provider="mock",
            voice_provider="",
            width=1080,
            height=1920,
            duration_s=20.0,
            scene_count=2,
            layout_archetype="cinematic_hero",
        )

    monkeypatch.setattr(ClipReelDesigner, "run", _fake_run)

    pipeline = MarketingPipeline()
    pipeline.run(
        BriefInput(
            tema="tema",
            publico_objetivo="audiencia",
            red_social="instagram",
            objetivo="branding",
        ),
        publish=False,
        content_format="user_clip_reel",
        drive_folder_id="folder123",
        revision_notes="usar el clip de la terraza",
    )

    assert captured["revision_notes"] == "usar el clip de la terraza"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def test_revise_endpoint_404_for_other_tenant(db_session, brief) -> None:
    from gateway.app.api.routes import revise_run_endpoint
    from gateway.app.schemas.contracts import ReviseRequest

    run = _pending_run(db_session, brief)
    with pytest.raises(HTTPException) as exc_info:
        revise_run_endpoint(
            run.id,
            ReviseRequest(notes="cambiar el color"),
            tenant_id="otro-tenant",
            db=db_session,
        )
    assert exc_info.value.status_code == 404


def test_revise_endpoint_409_when_not_pending(db_session, brief) -> None:
    from gateway.app.api.routes import revise_run_endpoint
    from gateway.app.schemas.contracts import ReviseRequest

    run = _pending_run(db_session, brief)
    run.status = "completed"
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        revise_run_endpoint(
            run.id,
            ReviseRequest(notes="cambiar el color"),
            tenant_id="demo-tenant",
            db=db_session,
        )
    assert exc_info.value.status_code == 409


def test_revise_request_rejects_blank_notes() -> None:
    from pydantic import ValidationError

    from gateway.app.schemas.contracts import ReviseRequest

    with pytest.raises(ValidationError):
        ReviseRequest(notes="  ")


def test_revise_endpoint_routes_video_run_to_video_queue(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    """Un reel no puede re-renderizarse inline: debe encolarse en video_render como el run original."""
    from workers import tasks as tasks_module

    captured: dict = {}

    def _fake_apply_async(*, args, kwargs, **extra):
        captured["args"] = args
        captured["kwargs"] = kwargs
        captured["extra"] = extra

    monkeypatch.setattr(tasks_module.execute_video_pipeline_task, "apply_async", _fake_apply_async)

    from gateway.app.api.routes import revise_run_endpoint
    from gateway.app.schemas.contracts import ReviseRequest

    run = _pending_run(
        db_session,
        brief,
        content_format="user_clip_reel",
        params={"drive_folder_id": "folder123"},
    )
    response = revise_run_endpoint(
        run.id,
        ReviseRequest(notes="cortar antes del aplauso"),
        tenant_id="demo-tenant",
        db=db_session,
    )

    assert response.status == "queued"
    assert captured["extra"].get("queue") == "video_render"
    assert captured["kwargs"]["revision_notes"] == "cortar antes del aplauso"
    assert captured["kwargs"]["drive_folder_id"] == "folder123"

    db_session.refresh(run)
    assert run.revision_count == 1


def test_revise_endpoint_failure_restores_pending_approval(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    """Si la regeneración falla, la versión anterior sigue siendo aprobable: no dejar el run 'failed'."""
    from agents.marketing_agents.designer import DesignerAgent
    from gateway.app.api.routes import revise_run_endpoint
    from gateway.app.schemas.contracts import ReviseRequest

    def _boom(self, brief_in, copy, strategy, **kwargs):
        raise RuntimeError("image_gen_failed: fal 500")

    monkeypatch.setattr(DesignerAgent, "run", _boom)

    run = _pending_run(db_session, brief)
    with pytest.raises(HTTPException) as exc_info:
        revise_run_endpoint(
            run.id,
            ReviseRequest(notes="mas contraste"),
            tenant_id="demo-tenant",
            db=db_session,
        )
    assert exc_info.value.status_code == 500

    db_session.refresh(run)
    assert run.status == "pending_approval"
    assert "revision_failed" in run.error_message


def test_revise_endpoint_feed_runs_inline(
    monkeypatch: pytest.MonkeyPatch, db_session, brief
) -> None:
    from agents.marketing_agents.designer import DesignerAgent
    from agents.marketing_agents.schemas import DesignOutput
    from gateway.app.api.routes import revise_run_endpoint
    from gateway.app.schemas.contracts import ReviseRequest

    def _fake_run(self, brief_in, copy, strategy, **kwargs):
        return DesignOutput(
            image_url="http://localhost:8000/static/images/inline.png",
            image_prompt="p",
            image_provider="mock",
            image_width=1080,
            image_height=1350,
            content_format="feed",
            layout_archetype="typographic_poster",
            layout_label="Poster",
            color_palette="",
            design_source="generated",
        )

    monkeypatch.setattr(DesignerAgent, "run", _fake_run)

    run = _pending_run(db_session, brief)
    response = revise_run_endpoint(
        run.id,
        ReviseRequest(notes="mas aire arriba"),
        tenant_id="demo-tenant",
        db=db_session,
    )

    assert response.status == "pending_approval"
    assert response.result["design"]["image_url"].endswith("inline.png")
