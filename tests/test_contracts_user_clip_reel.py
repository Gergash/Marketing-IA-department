"""Pruebas de RunRequest: content_format=user_clip_reel requiere drive_folder_id (model_validator)."""

import pytest
from pydantic import ValidationError

from gateway.app.schemas.contracts import RunRequest


def test_user_clip_reel_with_drive_folder_id_passes_validation() -> None:
    payload = RunRequest(brief_id=1, content_format="user_clip_reel", drive_folder_id="folder123")
    assert payload.content_format == "user_clip_reel"
    assert payload.drive_folder_id == "folder123"


def test_user_clip_reel_without_drive_folder_id_rejected_422() -> None:
    with pytest.raises(ValidationError, match="drive_folder_id"):
        RunRequest(brief_id=1, content_format="user_clip_reel")


def test_reel_without_drive_folder_id_still_valid_regression() -> None:
    """Regresion: el validator no debe exigir drive_folder_id a ningun otro content_format."""
    payload = RunRequest(brief_id=1, content_format="reel")
    assert payload.drive_folder_id is None


def test_content_format_column_fits_user_clip_reel_no_migration_needed() -> None:
    """user_clip_reel (14 caracteres) cabe en agent_runs.content_format String(16) — sin migracion Alembic."""
    from gateway.app.models.entities import AgentRun

    column = AgentRun.__table__.columns["content_format"]
    assert len("user_clip_reel") <= column.type.length
