"""Pruebas del flujo nativo LinkedIn vía publisher Python + OAuth DB token."""

from gateway.app.services.pipeline_service import _NATIVE_PYTHON_PLATFORMS, _OAUTH_PROVIDER_MAP


def test_oauth_provider_map_includes_linkedin() -> None:
    assert _OAUTH_PROVIDER_MAP["linkedin"] == "linkedin"
    assert _OAUTH_PROVIDER_MAP["instagram"] == "meta"


def test_native_python_platforms_includes_linkedin() -> None:
    assert "linkedin" in _NATIVE_PYTHON_PLATFORMS


def test_instagram_not_in_native_python_platforms() -> None:
    assert "instagram" not in _NATIVE_PYTHON_PLATFORMS
    assert "ig" not in _NATIVE_PYTHON_PLATFORMS
