"""Pruebas de _media_url y persistencia de GeneratedAsset.video_url para runs de reel."""

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gateway.app.db.session import Base
from gateway.app.models import AgentRun, Brief, GeneratedAsset, OAuthToken
from gateway.app.services.pipeline_service import _media_url, _persist_result, _publish_via_go


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline_service_video_test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_media_url_prefers_video_url_when_present() -> None:
    result = {"design": {"video_url": "http://localhost:8000/static/videos/x.mp4", "image_url": None}}
    assert _media_url(result) == "http://localhost:8000/static/videos/x.mp4"


def test_media_url_falls_back_to_image_url_when_no_video() -> None:
    result = {"design": {"image_url": "http://localhost:8000/static/images/x.png"}}
    assert _media_url(result) == "http://localhost:8000/static/images/x.png"


def test_media_url_empty_string_when_neither_present() -> None:
    assert _media_url({"design": {}}) == ""


def test_persist_result_stores_video_url_for_reel_design(db_session) -> None:
    brief = Brief(
        tenant_id="demo-tenant",
        tema="reel persist test",
        publico_objetivo="audiencia",
        red_social="instagram",
        objetivo="branding",
    )
    db_session.add(brief)
    db_session.commit()
    db_session.refresh(brief)

    run = AgentRun(tenant_id="demo-tenant", brief_id=brief.id, run_mode="async", status="running", content_format="reel")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    result = {
        "design": {
            "image_url": None,
            "video_url": "http://localhost:8000/static/videos/reel.mp4",
            "image_prompt": "",
        },
        "quality": {"approved": True},
    }

    _persist_result(db_session, run, result, "instagram")
    db_session.commit()

    asset = db_session.execute(select(GeneratedAsset).where(GeneratedAsset.run_id == run.id)).scalar_one()
    assert asset.video_url == "http://localhost:8000/static/videos/reel.mp4"
    assert asset.image_url == ""
    assert run.status == "completed"
    assert json.loads(run.result_json)["design"]["video_url"] == "http://localhost:8000/static/videos/reel.mp4"


def test_persist_result_still_stores_image_url_for_feed_design(db_session) -> None:
    """Regresion: runs de imagen deben seguir persistiendo image_url sin video_url."""
    brief = Brief(
        tenant_id="demo-tenant",
        tema="feed persist test",
        publico_objetivo="audiencia",
        red_social="instagram",
        objetivo="branding",
    )
    db_session.add(brief)
    db_session.commit()
    db_session.refresh(brief)

    run = AgentRun(tenant_id="demo-tenant", brief_id=brief.id, run_mode="sync", status="running", content_format="feed")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    result = {
        "design": {"image_url": "http://localhost:8000/static/images/feed.png", "image_prompt": "p"},
        "quality": {"approved": True},
    }

    _persist_result(db_session, run, result, "instagram")
    db_session.commit()

    asset = db_session.execute(select(GeneratedAsset).where(GeneratedAsset.run_id == run.id)).scalar_one()
    assert asset.image_url == "http://localhost:8000/static/images/feed.png"
    assert asset.video_url is None


def test_publish_via_go_includes_video_url_for_user_clip_reel(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_publish_via_go` debe incluir video_url en el payload para user_clip_reel (igual que reel)."""
    brief = Brief(
        tenant_id="demo-tenant",
        tema="clip reel publish test",
        publico_objetivo="audiencia",
        red_social="instagram",
        objetivo="branding",
    )
    db_session.add(brief)
    db_session.commit()
    db_session.refresh(brief)

    run = AgentRun(
        tenant_id="demo-tenant", brief_id=brief.id, run_mode="async", status="pending_approval",
        content_format="user_clip_reel",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    db_session.add(
        OAuthToken(
            tenant_id="demo-tenant", provider="meta", access_token="fake-access", account_id="fake-account",
        )
    )
    db_session.commit()

    result = {
        "copy": {"copy_final": "texto"},
        "design": {"video_url": "http://localhost:8000/static/videos/clipreel.mp4", "image_url": None},
    }

    captured_payload: dict = {}

    class _FakeResponse:
        is_success = True

        def json(self):
            return {"status": "success", "publication_url": "https://instagram.com/p/x", "platform_post_id": "1"}

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            captured_payload.update(json)
            return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "Client", lambda timeout=60: _FakeClient())

    outcome = _publish_via_go(result, brief, None, run, db_session)

    assert outcome == "success"
    assert captured_payload["content_format"] == "user_clip_reel"
    assert "video_url" in captured_payload
    assert captured_payload["video_url"].endswith("/static/videos/clipreel.mp4")
