"""Multi-cuenta social: N cuentas por proveedor, selector por run y publicación dirigida.

Cubre: convivencia de filas por (tenant, provider, account_id), callback OAuth que
agrega cuentas sin pisar las anteriores, _resolve_publish_token (cuenta del run,
validaciones y fallback legacy) y regresión de _publish_via_go sin selector.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gateway.app.api import auth_social
from gateway.app.db.session import Base
from gateway.app.models import AgentRun, Brief, OAuthToken
from gateway.app.schemas.contracts import RunRequest
from gateway.app.services.pipeline_service import _publish_via_go, _resolve_publish_token


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'multi_account_test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _account(
    *,
    tenant_id: str = "demo-tenant",
    provider: str = "meta",
    account_id: str = "ig-1",
    account_name: str | None = None,
    access_token: str = "tok",
    is_active: bool = True,
) -> OAuthToken:
    return OAuthToken(
        tenant_id=tenant_id,
        provider=provider,
        access_token=access_token,
        account_id=account_id,
        account_name=account_name,
        is_active=is_active,
    )


def _brief(db, red_social: str = "instagram") -> Brief:
    brief = Brief(
        tenant_id="demo-tenant",
        tema="multi cuenta",
        publico_objetivo="audiencia",
        red_social=red_social,
        objetivo="branding",
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return brief


def _run(db, brief, *, social_account_id: int | None = None) -> AgentRun:
    run = AgentRun(
        tenant_id="demo-tenant",
        brief_id=brief.id,
        run_mode="sync",
        status="pending_approval",
        content_format="feed",
        social_account_id=social_account_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Modelo: multi-fila por proveedor
# ---------------------------------------------------------------------------


def test_two_accounts_same_provider_coexist(db_session) -> None:
    db_session.add(_account(account_id="ig-cliente-a", account_name="@clienteA"))
    db_session.add(_account(account_id="ig-cliente-b", account_name="@clienteB"))
    db_session.commit()

    rows = db_session.execute(
        select(OAuthToken).where(OAuthToken.provider == "meta")
    ).scalars().all()
    assert {r.account_id for r in rows} == {"ig-cliente-a", "ig-cliente-b"}


def test_unique_constraint_tenant_provider_account(db_session) -> None:
    db_session.add(_account(account_id="ig-dup"))
    db_session.commit()
    db_session.add(_account(account_id="ig-dup"))
    with pytest.raises(Exception):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# Callback OAuth: agrega cuentas, no las pisa
# ---------------------------------------------------------------------------


def _callback_meta_with_accounts(db, monkeypatch, accounts: list[dict], state: str) -> None:
    auth_social._pending_states[state] = "demo-tenant"
    monkeypatch.setattr(
        auth_social,
        "_exchange_meta",
        lambda code, s: {"access_token": "user-token", "refresh_token": None, "expires_at": None},
    )
    monkeypatch.setattr(auth_social, "_fetch_meta_ig_accounts", lambda token, s: accounts)
    auth_social.oauth_callback("meta", state=state, db=db, code="fake-code")


def test_meta_callback_creates_row_per_page(db_session, monkeypatch) -> None:
    _callback_meta_with_accounts(
        db_session,
        monkeypatch,
        [
            {"account_id": "ig-1", "account_name": "@marca1", "page_id": "p1", "access_token": "page-tok-1"},
            {"account_id": "ig-2", "account_name": "@marca2", "page_id": "p2", "access_token": "page-tok-2"},
        ],
        state="s1",
    )

    rows = db_session.execute(select(OAuthToken)).scalars().all()
    assert len(rows) == 2
    by_id = {r.account_id: r for r in rows}
    assert by_id["ig-1"].access_token == "page-tok-1"  # Page token, no el user token
    assert by_id["ig-2"].account_name == "@marca2"
    assert all(r.is_active for r in rows)


def test_meta_callback_second_connect_does_not_overwrite_first(db_session, monkeypatch) -> None:
    _callback_meta_with_accounts(
        db_session, monkeypatch, [{"account_id": "ig-cliente-a", "account_name": "@clienteA"}], state="s1",
    )
    _callback_meta_with_accounts(
        db_session, monkeypatch, [{"account_id": "ig-cliente-b", "account_name": "@clienteB"}], state="s2",
    )

    rows = db_session.execute(select(OAuthToken)).scalars().all()
    assert {r.account_id for r in rows} == {"ig-cliente-a", "ig-cliente-b"}


def test_meta_callback_reconnect_same_account_refreshes_token(db_session, monkeypatch) -> None:
    _callback_meta_with_accounts(
        db_session, monkeypatch, [{"account_id": "ig-1", "access_token": "tok-viejo"}], state="s1",
    )
    _callback_meta_with_accounts(
        db_session, monkeypatch, [{"account_id": "ig-1", "access_token": "tok-nuevo"}], state="s2",
    )

    rows = db_session.execute(select(OAuthToken)).scalars().all()
    assert len(rows) == 1
    assert rows[0].access_token == "tok-nuevo"


# ---------------------------------------------------------------------------
# _resolve_publish_token
# ---------------------------------------------------------------------------


def test_resolve_uses_account_selected_in_run(db_session) -> None:
    a = _account(account_id="ig-a", access_token="tok-a")
    b = _account(account_id="ig-b", access_token="tok-b")
    db_session.add_all([a, b])
    db_session.commit()

    run = _run(db_session, _brief(db_session), social_account_id=b.id)
    row = _resolve_publish_token(db_session, run, "meta")
    assert row is not None
    assert row.account_id == "ig-b"
    assert row.access_token == "tok-b"


def test_resolve_rejects_account_of_other_tenant(db_session) -> None:
    other = _account(tenant_id="otro-tenant", account_id="ig-x")
    db_session.add(other)
    db_session.commit()

    run = _run(db_session, _brief(db_session), social_account_id=other.id)
    with pytest.raises(ValueError, match="no existe"):
        _resolve_publish_token(db_session, run, "meta")


def test_resolve_rejects_inactive_account(db_session) -> None:
    a = _account(account_id="ig-off", is_active=False)
    db_session.add(a)
    db_session.commit()

    run = _run(db_session, _brief(db_session), social_account_id=a.id)
    with pytest.raises(ValueError, match="desconectada"):
        _resolve_publish_token(db_session, run, "meta")


def test_resolve_rejects_provider_mismatch(db_session) -> None:
    a = _account(provider="linkedin", account_id="urn:li:person:1")
    db_session.add(a)
    db_session.commit()

    run = _run(db_session, _brief(db_session), social_account_id=a.id)
    with pytest.raises(ValueError, match="proveedor correcto"):
        _resolve_publish_token(db_session, run, "meta")


def test_resolve_fallback_without_selector_prefers_most_recent_active(db_session) -> None:
    old = _account(account_id="ig-vieja", access_token="tok-vieja")
    old.updated_at = datetime.utcnow() - timedelta(days=2)
    new = _account(account_id="ig-nueva", access_token="tok-nueva")
    inactive = _account(account_id="ig-inactiva", is_active=False)
    db_session.add_all([old, new, inactive])
    db_session.commit()

    run = _run(db_session, _brief(db_session), social_account_id=None)
    row = _resolve_publish_token(db_session, run, "meta")
    assert row is not None
    assert row.account_id == "ig-nueva"


def test_resolve_fallback_returns_none_without_accounts(db_session) -> None:
    run = _run(db_session, _brief(db_session), social_account_id=None)
    assert _resolve_publish_token(db_session, run, "meta") is None


# ---------------------------------------------------------------------------
# _publish_via_go: cuenta dirigida y regresión sin selector
# ---------------------------------------------------------------------------


class _FakeResponse:
    is_success = True

    def json(self):
        return {"status": "success", "publication_url": "https://instagram.com/p/x", "platform_post_id": "1"}


def _fake_go_client(captured: dict):
    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            captured.update(json)
            return _FakeResponse()

    return _FakeClient


def test_publish_via_go_uses_selected_account(db_session, monkeypatch) -> None:
    a = _account(account_id="ig-cliente-a", access_token="tok-a")
    b = _account(account_id="ig-cliente-b", access_token="tok-b")
    db_session.add_all([a, b])
    db_session.commit()

    brief = _brief(db_session)
    run = _run(db_session, brief, social_account_id=b.id)

    captured: dict = {}
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda timeout=60: _fake_go_client(captured)())

    result = {"copy": {"copy_final": "texto"}, "design": {"image_url": "http://localhost:8000/static/images/x.png"}}
    outcome = _publish_via_go(result, brief, None, run, db_session)

    assert outcome == "success"
    assert captured["account_id"] == "ig-cliente-b"
    assert captured["access_token"] == "tok-b"


def test_publish_via_go_without_selector_keeps_legacy_behavior(db_session, monkeypatch) -> None:
    """Regresión: run sin social_account_id publica con la única cuenta del provider."""
    db_session.add(_account(account_id="ig-unica", access_token="tok-unica"))
    db_session.commit()

    brief = _brief(db_session)
    run = _run(db_session, brief, social_account_id=None)

    captured: dict = {}
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda timeout=60: _fake_go_client(captured)())

    result = {"copy": {"copy_final": "texto"}, "design": {"image_url": "http://localhost:8000/static/images/x.png"}}
    outcome = _publish_via_go(result, brief, None, run, db_session)

    assert outcome == "success"
    assert captured["account_id"] == "ig-unica"
    assert captured["access_token"] == "tok-unica"


# ---------------------------------------------------------------------------
# Contrato RunRequest
# ---------------------------------------------------------------------------


def test_run_request_accepts_social_account_id() -> None:
    req = RunRequest(brief_id=1, social_account_id=7)
    assert req.social_account_id == 7


def test_run_request_social_account_defaults_to_none() -> None:
    assert RunRequest(brief_id=1).social_account_id is None
