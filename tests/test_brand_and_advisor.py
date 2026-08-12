"""Tests: manual de marca PDF + asesor creativo."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gateway.app.core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def brand_root(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from agents.marketing_agents import brand_manual

    monkeypatch.setattr(brand_manual, "_BRAND_ROOT", tmp_path / "brand")
    return tmp_path / "brand"


def test_brand_prompt_block_empty() -> None:
    from agents.marketing_agents.brand_manual import brand_prompt_block

    assert brand_prompt_block("") == ""
    assert "Brand manual" in brand_prompt_block("Colores: teal")


def test_save_and_load_brand_manual(brand_root, monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import brand_manual
    from agents.marketing_agents.brand_scan import BrandScanResult

    monkeypatch.setattr(
        brand_manual,
        "extract_pdf_text",
        lambda raw, max_pages=None: (
            "Identidad Acme. Tipografía Sans. No usar rojo chillón. " * 3,
            "pypdf",
        ),
    )
    monkeypatch.setattr(
        "agents.marketing_agents.brand_scan.scan_brand_pdf",
        lambda *a, **k: BrandScanResult(
            palette_hex=["#0F766E", "#111827"],
            logo_filenames=[],
            logo_urls=[],
            pages_scanned=1,
        ),
    )
    meta = brand_manual.save_brand_manual(
        "demo-tenant",
        b"%PDF-fake",
        original_filename="brand.pdf",
    )
    assert meta["char_count"] > 40
    assert meta["extraction_method"] == "pypdf"
    assert meta["palette_hex"] == ["#0F766E", "#111827"]
    assert "Acme" in meta["text_preview"]
    loaded = brand_manual.load_brand_text("demo-tenant")
    assert "Tipografía Sans" in loaded
    active = brand_manual.get_active_brand_meta("demo-tenant")
    assert active and active["id"] == meta["id"]
    assets = brand_manual.load_brand_visual_assets("demo-tenant")
    assert assets["palette_hex"] == ["#0F766E", "#111827"]
    assert brand_manual.clear_brand_manual("demo-tenant") is True
    assert brand_manual.load_brand_text("demo-tenant") == ""


def test_advisor_stub_without_llm(monkeypatch: pytest.MonkeyPatch, brand_root) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()

    from agents.marketing_agents.advisor import CreativeAdvisorAgent

    reply = CreativeAdvisorAgent().reply(
        "Quiero un reel para lanzar un evento",
        tenant_id="demo-tenant",
        brief_context={"tema": "Networking viernes", "red_social": "instagram"},
    )
    assert "reel" in reply.lower() or "video" in reply.lower() or "hook" in reply.lower()


def test_upload_brand_manual_endpoint(monkeypatch: pytest.MonkeyPatch, brand_root) -> None:
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()

    from agents.marketing_agents import brand_manual
    from agents.marketing_agents.brand_scan import BrandScanResult
    from gateway.app.main import app

    monkeypatch.setattr(
        brand_manual,
        "extract_pdf_text",
        lambda raw, max_pages=None: (
            "Manual de marca con tono profesional y cercano. Paleta azul. " * 5,
            "pypdf",
        ),
    )
    monkeypatch.setattr(
        "agents.marketing_agents.brand_scan.scan_brand_pdf",
        lambda *a, **k: BrandScanResult(
            palette_hex=["#1D4ED8"],
            logo_filenames=["x_logo_1.png"],
            logo_urls=["http://localhost:8000/static/uploads/brand/t/x_logo_1.png"],
            pages_scanned=2,
            embedded_images=1,
        ),
    )

    client = TestClient(app)
    files = {"file": ("manual.pdf", b"%PDF-1.4 fake", "application/pdf")}
    res = client.post("/api/briefs/upload-brand-manual", files=files)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["char_count"] > 40
    assert body["original_filename"] == "manual.pdf"
    assert body["palette_hex"] == ["#1D4ED8"]
    assert len(body["logo_urls"]) == 1

    got = client.get("/api/briefs/brand-manual")
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]
    assert got.json()["palette_hex"] == ["#1D4ED8"]

    deleted = client.delete("/api/briefs/brand-manual")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_advisor_chat_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()

    from gateway.app.main import app

    client = TestClient(app)
    res = client.post(
        "/api/advisor/chat",
        json={
            "message": "¿Story o feed para branding?",
            "brief_context": {"tema": "Café de especialidad", "objetivo": "branding"},
            "history": [],
        },
    )
    assert res.status_code == 200, res.text
    assert len(res.json()["reply"]) > 20


def test_brief_input_includes_brand_context(brand_root, monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.marketing_agents import brand_manual
    from agents.marketing_agents.brand_scan import BrandScanResult
    from gateway.app.models.entities import Brief
    from gateway.app.services.pipeline_service import _brief_input

    monkeypatch.setattr(
        brand_manual,
        "extract_pdf_text",
        lambda raw, max_pages=None: (
            "Voz de marca: cálida, nunca agresiva. " * 5,
            "pypdf",
        ),
    )
    monkeypatch.setattr(
        "agents.marketing_agents.brand_scan.scan_brand_pdf",
        lambda *a, **k: BrandScanResult(palette_hex=["#CA8A04"], pages_scanned=1),
    )
    brand_manual.save_brand_manual("t1", b"pdf", original_filename="a.pdf")

    brief = Brief(
        tenant_id="t1",
        tema="Evento demo largo suficiente",
        publico_objetivo="pymes",
        red_social="instagram",
        objetivo="branding",
        tono_marca="cercano",
        idioma="es",
    )
    dto = _brief_input(brief)
    assert "cálida" in dto.brand_context
    assert "#CA8A04" in dto.brand_palette
    assert dto.tenant_id == "t1"


def test_extract_falls_back_to_paddle_when_pypdf_short(
    brand_root, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_PROVIDER", "paddle")
    monkeypatch.setenv("OCR_MIN_TEXT_CHARS", "40")
    get_settings.cache_clear()

    from agents.marketing_agents import brand_manual, ocr_paddle

    monkeypatch.setattr(brand_manual, "extract_pdf_text_pypdf", lambda raw, max_pages=40: "corto")
    monkeypatch.setattr(
        ocr_paddle,
        "ocr_pdf_bytes",
        lambda raw, **kwargs: "Manual escaneado con tipografía corporativa y colores oficiales. " * 3,
    )
    # extract_pdf_text imports ocr_pdf_bytes from .ocr_paddle inside the function
    monkeypatch.setattr(
        "agents.marketing_agents.ocr_paddle.ocr_pdf_bytes",
        lambda raw, **kwargs: "Manual escaneado con tipografía corporativa y colores oficiales. " * 3,
    )

    text, method = brand_manual.extract_pdf_text(b"%PDF")
    assert method == "paddleocr"
    assert "tipografía corporativa" in text


def test_lines_from_ocr_result_classic_layout() -> None:
    from agents.marketing_agents.ocr_paddle import _lines_from_ocr_result

    classic = [[[None, ("Hola marca", 0.99)], [None, ("Color teal", 0.95)]]]
    assert _lines_from_ocr_result(classic) == ["Hola marca", "Color teal"]
