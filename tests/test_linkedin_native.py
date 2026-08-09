"""Flujo nativo LinkedIn: routing, API versionada /rest, expiry de token y guard de video."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.marketing_agents import social_providers
from gateway.app.api import auth_social
from gateway.app.api.auth_social import token_expiry_info
from gateway.app.db.session import Base
from gateway.app.models import AgentRun, Brief, OAuthToken
from gateway.app.services.pipeline_service import (
    _NATIVE_PYTHON_PLATFORMS,
    _OAUTH_PROVIDER_MAP,
    _assert_token_not_expired,
    _publish_via_linkedin,
)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_oauth_provider_map_includes_linkedin() -> None:
    assert _OAUTH_PROVIDER_MAP["linkedin"] == "linkedin"
    assert _OAUTH_PROVIDER_MAP["instagram"] == "meta"


def test_native_python_platforms_includes_linkedin() -> None:
    assert "linkedin" in _NATIVE_PYTHON_PLATFORMS


def test_instagram_not_in_native_python_platforms() -> None:
    assert "instagram" not in _NATIVE_PYTHON_PLATFORMS
    assert "ig" not in _NATIVE_PYTHON_PLATFORMS


# ---------------------------------------------------------------------------
# URL de autorización OAuth
# ---------------------------------------------------------------------------


def _linkedin_auth_url(monkeypatch, scopes: str = "openid profile w_member_social") -> str:
    settings = type("S", (), {
        "linkedin_client_id": "78k2b5dy01vj51",
        "linkedin_redirect_uri": "https://tunel.ngrok-free.dev/api/auth/callback/linkedin",
        "linkedin_scopes": scopes,
    })()
    monkeypatch.setattr(auth_social, "get_settings", lambda: settings)
    return auth_social.oauth_login("linkedin", tenant_id="demo-tenant").headers["location"]


def test_auth_url_uses_configured_scopes(monkeypatch) -> None:
    """Apps sin el producto OpenID usan r_basicprofile; no debe requerir cambio de código."""
    url = _linkedin_auth_url(monkeypatch, scopes="r_basicprofile w_member_social")
    assert "scope=r_basicprofile%20w_member_social" in url
    assert "openid" not in url


def test_auth_url_separates_scopes_with_percent20(monkeypatch) -> None:
    """LinkedIn no interpreta '+' como espacio: quote_plus rompe el consentimiento."""
    url = _linkedin_auth_url(monkeypatch)
    assert "scope=openid%20profile%20w_member_social" in url
    assert "+" not in url.split("scope=")[1].split("&")[0]


def test_auth_url_encodes_redirect_uri(monkeypatch) -> None:
    url = _linkedin_auth_url(monkeypatch)
    assert "redirect_uri=https%3A%2F%2Ftunel.ngrok-free.dev%2Fapi%2Fauth%2Fcallback%2Flinkedin" in url


# ---------------------------------------------------------------------------
# Cliente HTTP falso (el publisher abre su propio httpx.Client)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, headers=None, content=b"bytes"):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.headers = headers or {}
        self.content = content

    @property
    def is_success(self) -> bool:
        return self.status_code < 400

    @property
    def text(self) -> str:
        return str(self._json)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class _FakeClient:
    """Enruta por substring de URL y registra cada llamada para poder afirmar sobre ella."""

    def __init__(self, routes: dict, calls: list):
        self._routes = routes
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def _handle(self, method: str, url: str, headers=None, **_):
        self.calls.append({"method": method, "url": url, "headers": headers or {}})
        for fragment, resp in self._routes.items():
            if fragment in url:
                return resp
        raise AssertionError(f"URL inesperada en el test: {url}")

    def get(self, url, **kw):
        return self._handle("GET", url, **kw)

    def post(self, url, **kw):
        return self._handle("POST", url, **kw)

    def put(self, url, **kw):
        return self._handle("PUT", url, **kw)


def _install_fake_linkedin(monkeypatch, *, init_response=None, post_response=None) -> list:
    calls: list = []
    routes = {
        "static/images": _FakeResponse(headers={"content-type": "image/png"}, content=b"img"),
        "action=initializeUpload": init_response
        or _FakeResponse(
            status_code=200,
            json_data={"value": {"uploadUrl": "https://upload.linkedin.example/abc", "image": "urn:li:image:C123"}},
        ),
        "upload.linkedin.example": _FakeResponse(status_code=201),
        "/rest/posts": post_response
        or _FakeResponse(status_code=201, headers={"x-restli-id": "urn:li:share:999"}, content=b""),
    }
    # _linkedin hace `import httpx` dentro de la función: parchear el módulo alcanza.
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeClient(routes, calls))
    return calls


def _publish_linkedin(monkeypatch, **kw) -> dict:
    calls = _install_fake_linkedin(monkeypatch, **kw)
    result = social_providers._linkedin(
        "copy de prueba",
        "http://localhost:8000/static/images/pieza.png",
        "tok-123",
        "urn:li:person:ABC",
        "feed",
    )
    result["_calls"] = calls
    return result


# ---------------------------------------------------------------------------
# API versionada /rest (reemplaza /v2/assets + /v2/ugcPosts)
# ---------------------------------------------------------------------------


def test_linkedin_uses_versioned_rest_endpoints(monkeypatch) -> None:
    result = _publish_linkedin(monkeypatch)
    urls = [c["url"] for c in result["_calls"]]

    assert any("/rest/images?action=initializeUpload" in u for u in urls)
    assert any(u.endswith("/rest/posts") for u in urls)
    assert not any("/v2/assets" in u for u in urls), "registerUpload legacy no debe usarse"
    assert not any("ugcPosts" in u for u in urls), "ugcPosts legacy no debe usarse"


def test_linkedin_sends_version_header_on_rest_calls(monkeypatch) -> None:
    result = _publish_linkedin(monkeypatch)
    rest_calls = [c for c in result["_calls"] if "/rest/" in c["url"]]

    assert rest_calls, "debe haber llamadas a /rest"
    for call in rest_calls:
        assert call["headers"].get("LinkedIn-Version"), f"falta LinkedIn-Version en {call['url']}"
        assert call["headers"].get("X-Restli-Protocol-Version") == "2.0.0"


def test_linkedin_returns_post_id_from_restli_header(monkeypatch) -> None:
    result = _publish_linkedin(monkeypatch)
    assert result["platform_post_id"] == "urn:li:share:999"
    assert result["publication_url"] == "https://www.linkedin.com/feed/update/urn:li:share:999/"
    assert result["status"] == "published"


def test_linkedin_error_surfaces_response_body(monkeypatch) -> None:
    """El motivo real del rechazo vive en el body de LinkedIn; debe llegar al mensaje."""
    failing = _FakeResponse(status_code=403, json_data={"message": "Not enough permissions"})
    with pytest.raises(ValueError, match="Not enough permissions"):
        _publish_linkedin(monkeypatch, init_response=failing)


def test_linkedin_fails_when_initialize_upload_incomplete(monkeypatch) -> None:
    empty = _FakeResponse(status_code=200, json_data={"value": {}})
    with pytest.raises(ValueError, match="initializeUpload"):
        _publish_linkedin(monkeypatch, init_response=empty)


# ---------------------------------------------------------------------------
# Expiry del token
# ---------------------------------------------------------------------------


def test_token_expiry_info_without_expiry() -> None:
    info = token_expiry_info(None)
    assert info == {"expires_at": None, "expires_in_days": None, "is_expired": False, "expires_soon": False}


def test_token_expiry_info_expired() -> None:
    info = token_expiry_info(datetime.utcnow() - timedelta(days=1))
    assert info["is_expired"] is True
    assert info["expires_in_days"] == 0
    assert info["expires_soon"] is False


def test_token_expiry_info_expires_soon() -> None:
    info = token_expiry_info(datetime.utcnow() + timedelta(days=3))
    assert info["is_expired"] is False
    assert info["expires_soon"] is True


def test_token_expiry_info_healthy() -> None:
    info = token_expiry_info(datetime.utcnow() + timedelta(days=59))
    assert info["is_expired"] is False
    assert info["expires_soon"] is False
    assert info["expires_in_days"] == 59


def test_token_expiry_info_rounds_partial_day_up() -> None:
    """Quedan horas, no un día completo: mostrar 0 d se leería como caducado."""
    info = token_expiry_info(datetime.utcnow() + timedelta(hours=12))
    assert info["is_expired"] is False
    assert info["expires_in_days"] == 1


def test_exchange_linkedin_persists_expires_at(monkeypatch) -> None:
    """LinkedIn devuelve expires_in (~60 días); debe convertirse en expires_at."""
    import httpx

    routes = {"accessToken": _FakeResponse(json_data={"access_token": "tok", "expires_in": 5184000})}
    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeClient(routes, []))

    settings = type("S", (), {
        "linkedin_redirect_uri": "http://localhost:8000/api/auth/callback/linkedin",
        "linkedin_client_id": "id",
        "linkedin_client_secret": "secret",
    })()
    token_data = auth_social._exchange_linkedin("code-abc", settings)

    assert token_data["access_token"] == "tok"
    assert token_data["expires_at"] is not None
    remaining_days = (token_data["expires_at"] - datetime.utcnow()).days
    assert 58 <= remaining_days <= 60


def _fetch_account_with(monkeypatch, routes: dict) -> dict:
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeClient(routes, []))
    return auth_social._fetch_linkedin_account("tok")


def test_fetch_account_prefers_openid_userinfo(monkeypatch) -> None:
    account = _fetch_account_with(monkeypatch, {
        "userinfo": _FakeResponse(json_data={"sub": "ABC", "name": "Geronimo", "picture": "http://pic"}),
    })
    assert account == {
        "account_id": "urn:li:person:ABC",
        "account_name": "Geronimo",
        "profile_picture_url": "http://pic",
    }


def test_fetch_account_falls_back_to_v2_me_for_r_basicprofile(monkeypatch) -> None:
    """Apps sin producto OpenID: userinfo da 403 y la identidad sale de /v2/me."""
    account = _fetch_account_with(monkeypatch, {
        "userinfo": _FakeResponse(status_code=403, json_data={"message": "Not enough permissions"}),
        "/v2/me": _FakeResponse(json_data={
            "id": "XYZ",
            "localizedFirstName": "Geronimo",
            "localizedLastName": "Saldana",
        }),
    })
    assert account["account_id"] == "urn:li:person:XYZ"
    assert account["account_name"] == "Geronimo Saldana"


def test_fetch_account_without_any_profile_scope_explains_the_fix(monkeypatch) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException, match="LINKEDIN_SCOPES|OpenID"):
        _fetch_account_with(monkeypatch, {
            "userinfo": _FakeResponse(status_code=403, json_data={}),
            "/v2/me": _FakeResponse(status_code=403, json_data={}),
        })


def test_assert_token_not_expired_allows_valid_and_null() -> None:
    _assert_token_not_expired(OAuthToken(provider="linkedin", account_id="a", expires_at=None))
    _assert_token_not_expired(
        OAuthToken(provider="linkedin", account_id="a", expires_at=datetime.utcnow() + timedelta(days=5))
    )


def test_assert_token_not_expired_raises_with_actionable_message() -> None:
    row = OAuthToken(
        provider="linkedin",
        account_id="urn:li:person:ABC",
        account_name="Geronimo",
        expires_at=datetime.utcnow() - timedelta(days=2),
    )
    with pytest.raises(ValueError, match="Reconecta la cuenta en Integraciones"):
        _assert_token_not_expired(row)


# ---------------------------------------------------------------------------
# Guard de video: LinkedIn nativo solo soporta imagen
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'linkedin_test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


def _linkedin_run(db, content_format: str):
    db.add(OAuthToken(
        tenant_id="demo-tenant",
        provider="linkedin",
        access_token="tok",
        account_id="urn:li:person:ABC",
        is_active=True,
    ))
    brief = Brief(
        tenant_id="demo-tenant",
        tema="reel",
        publico_objetivo="audiencia",
        red_social="linkedin",
        objetivo="branding",
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    run = AgentRun(
        tenant_id="demo-tenant",
        brief_id=brief.id,
        run_mode="async",
        status="pending_approval",
        content_format=content_format,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return brief, run


def test_publish_via_linkedin_rejects_video_run(db_session) -> None:
    """Antes esto reventaba con AttributeError sobre image_url=None."""
    brief, run = _linkedin_run(db_session, "reel")
    result = {
        "copy": {"copy_final": "texto"},
        "design": {"image_url": None, "video_url": "http://localhost:8000/static/videos/x.mp4"},
    }

    with pytest.raises(ValueError, match="solo soporta imagen"):
        _publish_via_linkedin(db_session, result, brief, run, None)


def test_publish_via_linkedin_video_error_names_the_format(db_session) -> None:
    brief, run = _linkedin_run(db_session, "user_clip_reel")
    result = {"copy": {"copy_final": "texto"}, "design": {"video_url": "http://x/y.mp4"}}

    with pytest.raises(ValueError, match="user_clip_reel"):
        _publish_via_linkedin(db_session, result, brief, run, None)
