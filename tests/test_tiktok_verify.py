"""Verificación de dominio TikTok vía .txt en la raíz (ngrok → :8000)."""

from pathlib import Path

from fastapi.testclient import TestClient


def test_tiktok_verify_from_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TIKTOK_VERIFY_FILENAME", "tiktok-verify-demo.txt")
    monkeypatch.setenv("TIKTOK_VERIFY_CONTENT", "tiktok-verify-demo")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    from gateway.app.main import app

    client = TestClient(app)
    resp = client.get("/tiktok-verify-demo.txt")
    assert resp.status_code == 200
    assert resp.text.strip() == "tiktok-verify-demo"
    assert "text/plain" in resp.headers.get("content-type", "")


def test_tiktok_verify_from_disk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TIKTOK_VERIFY_FILENAME", "")
    monkeypatch.setenv("TIKTOK_VERIFY_CONTENT", "")
    from gateway.app.core.settings import get_settings

    get_settings.cache_clear()

    verify_dir = Path(__file__).resolve().parents[1] / "static" / "tiktok-verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    name = "tiktokdiskfile999.txt"
    path = verify_dir / name
    path.write_text("tiktokdiskfile999\n", encoding="utf-8")
    try:
        from gateway.app.main import app

        client = TestClient(app)
        resp = client.get(f"/{name}")
        assert resp.status_code == 200
        assert resp.text.strip() == "tiktokdiskfile999"
    finally:
        path.unlink(missing_ok=True)


def test_tiktok_verify_rejects_non_tiktok_names() -> None:
    from gateway.app.main import app

    client = TestClient(app)
    assert client.get("/random-file.txt").status_code == 404
    assert client.get("/terminos").status_code == 200  # legales intactos
