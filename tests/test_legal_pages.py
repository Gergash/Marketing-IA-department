"""Páginas legales públicas para TikTok / App Review."""

from pathlib import Path

from fastapi.testclient import TestClient


def test_terminos_and_privacidad_are_public_html() -> None:
    from gateway.app.main import app

    client = TestClient(app)
    for path in ("/terminos", "/privacidad", "/terms", "/privacy"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "text/html" in resp.headers.get("content-type", "")
        body = resp.text.lower()
        assert len(body) > 200
        assert "marketing depa" in body


def test_legal_pdfs_are_public() -> None:
    from gateway.app.main import app

    client = TestClient(app)
    for path in ("/terminos.pdf", "/privacidad.pdf"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "pdf" in resp.headers.get("content-type", "").lower()
        assert resp.content[:4] == b"%PDF"


def test_legal_html_files_exist() -> None:
    root = Path(__file__).resolve().parents[1] / "static" / "legal"
    assert (root / "terminos.html").is_file()
    assert (root / "privacidad.html").is_file()
    assert (root / "terminos.pdf").is_file()
    assert (root / "privacidad.pdf").is_file()
