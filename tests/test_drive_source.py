"""Pruebas de auth_social.py (proveedor google) + drive_source.py: OAuth Drive, refresh, listado/descarga.

Todo el I/O de red (Google OAuth, Drive API) está mockeado — sin red real en tests.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from agents.marketing_agents import drive_source as ds
from gateway.app.api import auth_social
from gateway.app.core.settings import get_settings
from gateway.app.db.session import Base
from gateway.app.models import OAuthToken


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'drive_test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _token_row(
    tenant_id: str = "demo-tenant",
    *,
    expires_at: datetime | None = None,
    refresh_token: str | None = "refresh-abc",
    access_token: str = "access-abc",
) -> OAuthToken:
    return OAuthToken(
        tenant_id=tenant_id,
        provider="google",
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        account_id="user@example.com",
    )


# ---------------------------------------------------------------------------
# OAuth: login + callback (auth_social.py, proveedor google)
# ---------------------------------------------------------------------------


def test_google_login_url_requests_drive_readonly_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-client-id")
    get_settings.cache_clear()

    response = auth_social.oauth_login("google", tenant_id="demo-tenant")
    location = response.headers["location"]
    assert "drive.readonly" in location
    assert "access_type=offline" in location


def test_google_callback_stores_access_and_refresh_token(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-secret")
    get_settings.cache_clear()

    state = "fixed-state"
    auth_social._pending_states[state] = "demo-tenant"

    monkeypatch.setattr(
        auth_social,
        "_exchange_google",
        lambda code, s: {
            "access_token": "fake-access",
            "refresh_token": "fake-refresh",
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        },
    )
    monkeypatch.setattr(auth_social, "_fetch_google_account", lambda token: "user@example.com")

    auth_social.oauth_callback("google", state=state, db=db_session, code="fake-code")

    token = db_session.execute(
        select(OAuthToken).where(OAuthToken.tenant_id == "demo-tenant", OAuthToken.provider == "google")
    ).scalar_one_or_none()
    assert token is not None
    assert token.access_token == "fake-access"
    assert token.refresh_token == "fake-refresh"
    assert token.account_id == "user@example.com"


# ---------------------------------------------------------------------------
# drive_source.py: refresh headless + listado/descarga
# ---------------------------------------------------------------------------


def test_no_stored_token_raises_reconnect_error(db_session) -> None:
    with pytest.raises(ds.DriveAuthError, match="Reconecta"):
        ds.list_and_download_clips(db_session, "demo-tenant", "folder123", run_id=1)


def test_refresh_rejected_raises_reconnect_error_no_silent_retry(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _token_row(expires_at=datetime.utcnow() - timedelta(hours=1))
    db_session.add(token)
    db_session.commit()

    calls = {"count": 0}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            raise RuntimeError("400 Bad Request")

    def _fake_post(self, url, *, data=None, **kwargs):
        calls["count"] += 1
        return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx.Client, "post", _fake_post)

    with pytest.raises(ds.DriveAuthError, match="Reconecta"):
        ds.list_and_download_clips(db_session, "demo-tenant", "folder123", run_id=1)
    assert calls["count"] == 1  # sin reintento silencioso


def test_folder_with_3_videos_downloads_all(db_session, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    token = _token_row(expires_at=datetime.utcnow() + timedelta(hours=1))
    db_session.add(token)
    db_session.commit()

    monkeypatch.setattr(ds, "_STATIC_CLIPS_DIR", tmp_path / "clips")

    files = [
        {"id": "f1", "name": "clip1.mp4", "mimeType": "video/mp4"},
        {"id": "f2", "name": "clip2.mp4", "mimeType": "video/mp4"},
        {"id": "f3", "name": "clip3.mp4", "mimeType": "video/mp4"},
    ]
    monkeypatch.setattr(ds, "_list_folder_files", lambda access_token, folder_id: files)

    downloaded_ids: list[str] = []

    def _fake_download(access_token, file_id, dest_path):
        downloaded_ids.append(file_id)
        dest_path.write_bytes(b"fake-video-bytes")

    monkeypatch.setattr(ds, "_download_file", _fake_download)

    clips = ds.list_and_download_clips(db_session, "demo-tenant", "folder123", run_id=42)
    assert len(clips) == 3
    assert sorted(downloaded_ids) == ["f1", "f2", "f3"]
    for clip in clips:
        assert Path(clip.path).exists()
        assert "42" in clip.path


def test_empty_folder_raises_before_transcription(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    token = _token_row(expires_at=datetime.utcnow() + timedelta(hours=1))
    db_session.add(token)
    db_session.commit()

    monkeypatch.setattr(ds, "_list_folder_files", lambda access_token, folder_id: [])

    with pytest.raises(RuntimeError, match="no_clips_found"):
        ds.list_and_download_clips(db_session, "demo-tenant", "folder123", run_id=1)


def test_mixed_video_and_nonvideo_only_videos_downloaded(
    db_session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _token_row(expires_at=datetime.utcnow() + timedelta(hours=1))
    db_session.add(token)
    db_session.commit()

    monkeypatch.setattr(ds, "_STATIC_CLIPS_DIR", tmp_path / "clips")

    files = [
        {"id": "f1", "name": "clip1.mp4", "mimeType": "video/mp4"},
        {"id": "f2", "name": "notes.txt", "mimeType": "text/plain"},
        {"id": "f3", "name": "photo.jpg", "mimeType": "image/jpeg"},
    ]
    monkeypatch.setattr(ds, "_list_folder_files", lambda access_token, folder_id: files)

    downloaded_ids: list[str] = []

    def _fake_download(access_token, file_id, dest_path):
        downloaded_ids.append(file_id)
        dest_path.write_bytes(b"fake-video-bytes")

    monkeypatch.setattr(ds, "_download_file", _fake_download)

    clips = ds.list_and_download_clips(db_session, "demo-tenant", "folder123", run_id=7)
    assert len(clips) == 1
    assert downloaded_ids == ["f1"]


def test_malicious_filename_is_sanitized_no_path_traversal(
    db_session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El nombre viene crudo de Drive; un nombre tipo '../../etc/passwd' no debe escapar dest_dir."""
    token = _token_row(expires_at=datetime.utcnow() + timedelta(hours=1))
    db_session.add(token)
    db_session.commit()

    clips_root = tmp_path / "clips"
    monkeypatch.setattr(ds, "_STATIC_CLIPS_DIR", clips_root)

    files = [{"id": "f1", "name": "../../../etc/passwd", "mimeType": "video/mp4"}]
    monkeypatch.setattr(ds, "_list_folder_files", lambda access_token, folder_id: files)

    def _fake_download(access_token, file_id, dest_path):
        dest_path.write_bytes(b"fake-video-bytes")

    monkeypatch.setattr(ds, "_download_file", _fake_download)

    clips = ds.list_and_download_clips(db_session, "demo-tenant", "folder123", run_id=99)
    assert len(clips) == 1
    dest_dir = (clips_root / "99").resolve()
    resolved_path = Path(clips[0].path).resolve()
    assert resolved_path.parent == dest_dir
    assert ".." not in Path(clips[0].filename).parts


def test_duplicate_filenames_do_not_overwrite_each_other(
    db_session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dos archivos de Drive con el mismo `name` deben descargarse a rutas distintas (prefijo con el id de Drive)."""
    token = _token_row(expires_at=datetime.utcnow() + timedelta(hours=1))
    db_session.add(token)
    db_session.commit()

    monkeypatch.setattr(ds, "_STATIC_CLIPS_DIR", tmp_path / "clips")

    files = [
        {"id": "f1", "name": "clip.mp4", "mimeType": "video/mp4"},
        {"id": "f2", "name": "clip.mp4", "mimeType": "video/mp4"},
    ]
    monkeypatch.setattr(ds, "_list_folder_files", lambda access_token, folder_id: files)

    def _fake_download(access_token, file_id, dest_path):
        dest_path.write_bytes(f"bytes-{file_id}".encode())

    monkeypatch.setattr(ds, "_download_file", _fake_download)

    clips = ds.list_and_download_clips(db_session, "demo-tenant", "folder123", run_id=5)
    assert len(clips) == 2
    paths = {clip.path for clip in clips}
    assert len(paths) == 2  # rutas distintas, sin pisarse
    filenames = {clip.filename for clip in clips}
    assert filenames == {"f1_clip.mp4", "f2_clip.mp4"}
    for clip in clips:
        file_id = clip.filename.split("_", 1)[0]
        assert Path(clip.path).read_bytes() == f"bytes-{file_id}".encode()
