"""Pruebas del pipeline completo (sin publicación y con mock de publicación)."""

import pytest

from agents.marketing_agents import BriefInput, MarketingPipeline


@pytest.fixture(autouse=True)
def _mock_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("SOCIAL_PROVIDER", "mock")


def test_pipeline_without_publish() -> None:
    """El pipeline debe producir estrategia, copy, diseño y traza QA sin llamar al publicador."""
    pipeline = MarketingPipeline()
    brief = BriefInput(
        tema="automatizacion de contenido",
        publico_objetivo="duenos de negocio",
        red_social="instagram",
        objetivo="branding",
    )
    result = pipeline.run(brief, publish=False)
    assert "strategy" in result
    assert "copy" in result
    assert "design" in result
    assert "copy_qa_trace" in result
    assert isinstance(result["copy_qa_trace"], list)
    assert result["publish_result"] is None
    assert result["design"].get("layout_archetype")
    assert result["design"].get("image_width") == 1080
    assert result["design"].get("image_height") == 1350


def test_pipeline_with_publish() -> None:
    """Con publish=True y proveedor mock, debe existir `publish_result` no nulo."""
    pipeline = MarketingPipeline()
    brief = BriefInput(
        tema="agentes IA para marketing",
        publico_objetivo="equipos B2B",
        red_social="instagram",
        objetivo="ventas",
    )
    result = pipeline.run(brief, publish=True, idempotency_key="abc123")
    assert result["publish_result"] is not None
