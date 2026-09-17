"""Panel de administrador: acceso por rol/ADMIN_EMAILS, métricas de usuarios,
reparto de uso por proveedor, reset de contraseña y regla de no exponer password_hash.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gateway.app.api import admin as admin_api
from gateway.app.core.auth import require_admin, require_auth
from gateway.app.db.session import Base
from gateway.app.models.entities import AgentRun, ApiUsageEvent, AppUser, CreditWallet, PaymentRecord
from gateway.app.services.auth_users import authenticate_user, _hash_password


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_panel_test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _make_user(
    db,
    *,
    email: str,
    tenant_id: str,
    is_admin: bool = False,
    is_active: bool = True,
    password: str = "supersecret1",
) -> AppUser:
    user = AppUser(
        email=email,
        password_hash=_hash_password(password),
        tenant_id=tenant_id,
        full_name="",
        is_admin=is_admin,
        is_active=is_active,
    )
    db.add(user)
    db.add(CreditWallet(tenant_id=tenant_id, balance=0))
    db.commit()
    db.refresh(user)
    return user


def test_non_admin_gets_403_on_overview(db_session) -> None:
    user = _make_user(db_session, email="plain@example.com", tenant_id="t-plain")
    with pytest.raises(HTTPException) as exc_info:
        require_admin(tenant_id=user.tenant_id, db=db_session)
    assert exc_info.value.status_code == 403


def test_admin_emails_env_grants_access_without_is_admin_flag(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gateway.app.core.settings import get_settings

    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com, other@example.com")
    get_settings.cache_clear()
    user = _make_user(db_session, email="boss@example.com", tenant_id="t-boss", is_admin=False)

    resolved = require_admin(tenant_id=user.tenant_id, db=db_session)
    assert resolved.id == user.id


def test_admin_users_endpoint_reports_correct_balances(db_session) -> None:
    admin = _make_user(db_session, email="admin@example.com", tenant_id="t-admin", is_admin=True)
    target = _make_user(db_session, email="user@example.com", tenant_id="t-user")

    wallet = db_session.query(CreditWallet).filter_by(tenant_id="t-user").one()
    wallet.balance = 40
    db_session.add(PaymentRecord(tenant_id="t-user", reference="ref-1", amount_cop=99000, credits_added=100, status="paid"))
    db_session.add(
        ApiUsageEvent(tenant_id="t-user", provider="venice", operation="image_generate", credits_cost=2)
    )
    db_session.add(
        ApiUsageEvent(tenant_id="t-user", provider="fal", operation="image_generate", credits_cost=1)
    )
    db_session.add(AgentRun(tenant_id="t-user", brief_id=0, status="completed", content_format="feed"))
    db_session.commit()

    result = admin_api.admin_users(query="", limit=50, offset=0, admin=admin, db=db_session)
    items = {i["email"]: i for i in result["items"]}
    assert result["total"] == 2
    target_item = items["user@example.com"]
    assert target_item["credits_balance"] == 40
    assert target_item["credits_consumed"] == 3
    assert target_item["runs_total"] == 1
    assert target_item["paid_total_cop"] == 99000
    assert target_item["password_algo"] == "pbkdf2_sha256"


def test_usage_by_provider_shares_sum_to_100(db_session) -> None:
    from gateway.app.services.usage_service import usage_by_provider

    db_session.add_all(
        [
            ApiUsageEvent(tenant_id="t-a", provider="venice", operation="image_generate", credits_cost=2),
            ApiUsageEvent(tenant_id="t-a", provider="venice", operation="image_generate", credits_cost=2),
            ApiUsageEvent(tenant_id="t-a", provider="venice", operation="image_generate", credits_cost=2),
            ApiUsageEvent(tenant_id="t-a", provider="fal", operation="image_generate", credits_cost=2),
        ]
    )
    db_session.commit()

    rows = usage_by_provider(db_session)
    total_pct = sum(r["share_pct"] for r in rows)
    assert 99.0 <= total_pct <= 100.01
    by_provider = {r["provider"]: r for r in rows}
    assert by_provider["venice"]["events"] == 3
    assert by_provider["fal"]["events"] == 1


def test_reset_password_changes_hash_and_new_password_logs_in(db_session) -> None:
    admin = _make_user(db_session, email="admin2@example.com", tenant_id="t-admin2", is_admin=True)
    target = _make_user(db_session, email="locked@example.com", tenant_id="t-locked", password="oldpassword1")
    old_hash = target.password_hash

    resp = admin_api.admin_reset_password(target.id, admin=admin, db=db_session)
    db_session.refresh(target)
    assert target.password_hash != old_hash

    logged_in = authenticate_user(db_session, email="locked@example.com", password=resp.temporary_password)
    assert logged_in is not None
    assert logged_in.id == target.id


def test_no_endpoint_response_contains_password_hash(db_session) -> None:
    admin = _make_user(db_session, email="admin3@example.com", tenant_id="t-admin3", is_admin=True)
    target = _make_user(db_session, email="check@example.com", tenant_id="t-check")

    users_resp = admin_api.admin_users(query="", limit=50, offset=0, admin=admin, db=db_session)
    detail_resp = admin_api.admin_user_detail(target.id, admin=admin, db=db_session)

    for item in users_resp["items"]:
        assert "password_hash" not in item
    assert "password_hash" not in detail_resp
    assert detail_resp["password_algo"] == "pbkdf2_sha256"


def test_inactive_user_gets_403_via_require_auth(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.app.core.settings import get_settings
    from gateway.app.services.auth_users import create_access_token

    monkeypatch.setenv("STAGING_SAAS_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    user = _make_user(db_session, email="blocked@example.com", tenant_id="t-blocked", is_active=False)
    token = create_access_token(email=user.email, tenant_id=user.tenant_id)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        require_auth(credentials=credentials, db=db_session)
    assert exc_info.value.status_code == 403
