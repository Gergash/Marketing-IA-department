from agents.marketing_agents import BriefInput, MarketingPipeline


def test_pipeline_without_publish() -> None:
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


def test_pipeline_with_publish() -> None:
    pipeline = MarketingPipeline()
    brief = BriefInput(
        tema="agentes IA para marketing",
        publico_objetivo="equipos B2B",
        red_social="instagram",
        objetivo="ventas",
    )
    result = pipeline.run(brief, publish=True, idempotency_key="abc123")
    assert result["publish_result"] is not None
