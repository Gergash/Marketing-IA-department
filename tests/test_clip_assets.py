"""Pruebas de clip_assets.py: resolucion de URL publica desde ruta absoluta bajo static/."""

from pathlib import Path

from agents.marketing_agents.clip_assets import clip_public_url


def test_clip_public_url_maps_static_path_to_url() -> None:
    static_root = Path(__file__).resolve().parents[1] / "static"
    local_path = static_root / "uploads" / "clips" / "42" / "f1_clip.mp4"

    url = clip_public_url(str(local_path))

    assert url == "http://localhost:8000/static/uploads/clips/42/f1_clip.mp4"


def test_clip_public_url_returns_unchanged_path_when_outside_static() -> None:
    outside_path = "/tmp/some/other/place/clip.mp4"

    url = clip_public_url(outside_path)

    assert url == outside_path
