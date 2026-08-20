"""Publicación nativa en X (Twitter): OAuth 1.0a + media + tweet."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qsl

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.marketing_agents import social_providers
from gateway.app.api import auth_social
from gateway.app.db.session import Base
from gateway.app.models import AgentRun, Brief
from gateway.app.services.pipeline_service import (
    _NATIVE_PYTHON_PLATFORMS,
    _OAUTH_PROVIDER_MAP,
    _publish_via_x,
)


def test_oauth_provider_map_includes_x() -> None:
    assert _OAUTH_PROVIDER_MAP["x"] == "x"
    assert _OAUTH_PROVIDER_MAP["twitter"] == "x"


def test_native_python_platforms_includes_x() -> None:
    assert "x" in _NATIVE_PYTHON_PLATFORMS
    assert "twitter" in _NATIVE_PYTHON_PLATFORMS


class _FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, text="", content=b"", headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text or ("" if json_data is None else str(json_data))
        self.content = content
        self.headers = headers or {}
        self.is_success = 200 <= status_code < 300

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class _FakeClient:
    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        for prefix, resp in self.routes.items():
            if prefix in url:
                return resp if not callable(resp) else resp("GET", url, kwargs)
        return _FakeResponse(status_code=404, text=f"no mock for GET {url}")

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        for prefix, resp in self.routes.items():
            if prefix in url:
                return resp if not callable(resp) else resp("POST", url, kwargs)
        return _FakeResponse(status_code=404, text=f"no mock for POST {url}")


def test_x_login_requires_keys(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_social,
        "get_settings",
        lambda: SimpleNamespace(x_api_key="", x_api_secret=""),
    )
    with pytest.raises(Exception) as exc:
        auth_social.oauth_login("x", tenant_id="demo-tenant")
    assert "X_API_KEY" in str(exc.value.detail)


def test_x_login_redirects_to_authorize(monkeypatch) -> None:
    settings = SimpleNamespace(
        x_api_key="ck",
        x_api_secret="cs",
        x_redirect_uri="https://tunel.ngrok-free.dev/api/auth/callback/x",
    )
    monkeypatch.setattr(auth_social, "get_settings", lambda: settings)
    monkeypatch.setattr(
        auth_social,
        "_x_request_token",
        lambda s: {"oauth_token": "req-tok", "oauth_token_secret": "req-sec"},
    )
    auth_social._pending_x_request_tokens.clear()
    loc = auth_social.oauth_login("x", tenant_id="demo-tenant").headers["location"]
    assert loc.startswith("https://api.twitter.com/oauth/authorize?")
    assert "oauth_token=req-tok" in loc
    assert auth_social._pending_x_request_tokens["req-tok"]["tenant_id"] == "demo-tenant"
    assert auth_social._pending_x_request_tokens["req-tok"]["oauth_token_secret"] == "req-sec"


def test_x_access_token_parses_user(monkeypatch) -> None:
    settings = SimpleNamespace(x_api_key="ck", x_api_secret="cs")
    monkeypatch.setattr(
        auth_social,
        "_x_signed_post",
        lambda url, client: "oauth_token=AT&oauth_token_secret=AS&user_id=42&screen_name=depa",
    )
    token_data, account = auth_social._x_access_token(
        settings,
        oauth_token="rt",
        oauth_token_secret="rs",
        oauth_verifier="vv",
    )
    assert token_data["access_token"] == "AT"
    assert token_data["refresh_token"] == "AS"
    assert account["account_id"] == "42"
    assert account["account_name"] == "@depa"


def test_x_twitter_uploads_media_and_tweets(monkeypatch) -> None:
    import httpx as httpx_mod

    monkeypatch.setattr(
        httpx_mod,
        "Client",
        lambda **kw: _FakeClient(
            {
                "http://img.example": _FakeResponse(
                    content=b"IMG", headers={"content-type": "image/png"}
                ),
                "upload.twitter.com": lambda m, u, k: _FakeResponse(
                    json_data={"media_id_string": "999"}
                ),
                "api.twitter.com/2/tweets": lambda m, u, k: _FakeResponse(
                    json_data={"data": {"id": "12345"}}
                ),
            }
        ),
    )
    monkeypatch.setattr(
        social_providers,
        "_x_oauth1_auth_header",
        lambda *a, **k: {"Authorization": "OAuth fake"},
    )

    result = social_providers._x_twitter(
        "Hola X #test",
        "http://img.example/a.png",
        "atok",
        "asec",
        "feed",
    )
    assert result["status"] == "published"
    assert result["platform_post_id"] == "12345"
    assert "12345" in result["publication_url"]


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'x_test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


def test_publish_via_x_requires_connected_account(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "gateway.app.services.pipeline_service.get_settings",
        lambda: SimpleNamespace(
            x_api_key="ck",
            x_api_secret="cs",
            public_image_base_url="http://localhost:8000",
        ),
    )
    brief = Brief(
        tenant_id="demo-tenant",
        tema="tweet",
        publico_objetivo="audiencia",
        red_social="x",
        objetivo="branding",
    )
    db_session.add(brief)
    db_session.commit()
    db_session.refresh(brief)
    run = AgentRun(
        tenant_id="demo-tenant",
        brief_id=brief.id,
        run_mode="async",
        status="pending_approval",
        content_format="feed",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    with pytest.raises(ValueError, match="No hay cuenta de X"):
        _publish_via_x(
            db_session,
            {
                "copy": {"copy_final": "hi"},
                "design": {"image_url": "http://localhost:8000/static/images/a.jpg"},
            },
            brief,
            run,
            None,
        )


def test_request_token_parse_qsl_roundtrip() -> None:
    raw = "oauth_token=abc&oauth_token_secret=def&oauth_callback_confirmed=true"
    data = dict(parse_qsl(raw))
    assert data["oauth_token"] == "abc"
    assert data["oauth_callback_confirmed"] == "true"
