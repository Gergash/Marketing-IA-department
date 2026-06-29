"""Pipeline principal: orquestación lineal + subgrafo LangGraph copy/QA."""

from .copywriter import CopywriterAgent
from .designer import DesignerAgent
from .graph_copy_qa import build_copy_qa_graph, invoke_copy_qa
from .publisher import PublisherAgent
from .quality import ContentQualityGuard
from .schemas import BriefInput
from .strategist import ContentStrategistAgent


class MarketingPipeline:
    """Orquestación híbrida: tramo lineal en Python + bucle Copy/QA en LangGraph."""

    def __init__(self, *, max_copy_qa_attempts: int = 3) -> None:
        """Instancia agentes y compila una vez el subgrafo LangGraph copy/QA con el tope de reintentos dado."""
        self.strategist = ContentStrategistAgent()
        self.copywriter = CopywriterAgent()
        self.designer = DesignerAgent()
        self.publisher = PublisherAgent()
        self.quality_guard = ContentQualityGuard()
        self._max_copy_qa_attempts = max_copy_qa_attempts
        self._copy_qa_graph = build_copy_qa_graph(self.copywriter, self.quality_guard)

    def run(
        self,
        brief: BriefInput,
        *,
        publish: bool,
        idempotency_key: str | None = None,
        content_format: str = "feed",
        image_provider: str | None = None,
        archetype_override: str | None = None,
    ) -> dict:
        """Ejecuta estratega → grafo copy/QA → diseño → publicación opcional; devuelve dict serializable."""
        strategy = self.strategist.run(brief)
        gout = invoke_copy_qa(
            self._copy_qa_graph,
            brief=brief,
            strategy=strategy,
            max_attempts=self._max_copy_qa_attempts,
        )
        copy = gout["copy"]
        quality = gout["quality"]
        copy_qa_trace = list(gout.get("events", []))

        design = self.designer.run(
            brief,
            copy,
            strategy,
            image_provider=image_provider,
            content_format=content_format,
            archetype_override=archetype_override,
        )

        publish_result = None
        if publish and quality.approved:
            publish_result = self.publisher.run(
                brief.red_social,
                copy,
                design,
                idempotency_key=idempotency_key,
                content_format=content_format,
            )

        return {
            "strategy": strategy.model_dump(),
            "copy": copy.model_dump(),
            "design": design.model_dump(),
            "quality": quality.model_dump(),
            "copy_qa_trace": copy_qa_trace,
            "publish_result": publish_result.model_dump() if publish_result else None,
        }
