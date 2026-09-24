"""Auth0-only SaaS: local register/login gone; Auth0 JWT provisions AppUser.

Cubre: /register|/login → 410, upsert_user_from_auth0 + wallet seed,
require_auth exige Auth0 cuando STAGING_SAAS + AUTH0_* están activos.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gateway.app.api import auth_users as auth_api
from gateway.app.core import auth as core_auth
from gateway.app.db.session import Base
from gateway.app.models.entities import AppUser, CreditWallet
from gateway.app.services.auth0_jwt import upsert_user_from_auth0


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'auth0_only.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_local_register_and_login_return_410() -> None:
    with pytest.raises(HTTPException) as reg:
        auth_api.register_removed()
    assert reg.value.status_code == 410
    with pytest.raises(HTTPException) as login:
        auth_api.login_removed()
    assert login.value.status_code == 410


def test_upsert_user_from_auth0_creates_wallet(db_session) -> None:
    user = upsert_user_from_auth0(
        db_session,
        auth0_sub="auth0|abc123",
        email="owner@example.com",
        full_name="Owner",
    )
    assert user.auth0_sub == "auth0|abc123"
    assert user.email == "owner@example.com"
    assert (user.password_hash or "") == ""
    wallet = db_session.query(CreditWallet).filter_by(tenant_id=user.tenant_id).one()
    assert wallet.balance == 100  # STAGING_SEED_CREDITS default

    again = upsert_user_from_auth0(
        db_session,
        auth0_sub="auth0|abc123",
        email="owner@example.com",
        full_name="Owner",
    )
    assert again.id == user.id


def test_require_auth_uses_auth0_when_configured(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.app.core.settings import get_settings

    monkeypatch.setenv("STAGING_SAAS_ENABLED", "true")
    monkeypatch.setenv("AUTH0_DOMAIN", "dev-ayl6gsakmvf7rb27.us.auth0.com")
    monkeypatch.setenv("AUTH0_CLIENT_ID", "loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L")
    get_settings.cache_clear()

    def fake_resolve(db, token):
        user = upsert_user_from_auth0(db, auth0_sub="auth0|x", email="a@b.co", full_name="")
        return user.tenant_id, user

    monkeypatch.setattr("gateway.app.services.auth0_jwt.resolve_tenant_from_auth0_token", fake_resolve)

    from fastapi.security import HTTPAuthorizationCredentials

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="a.b.c")
    tenant = core_auth.require_auth(credentials=creds, db=db_session)
    assert tenant
    assert db_session.query(AppUser).filter_by(auth0_sub="auth0|x").one()
