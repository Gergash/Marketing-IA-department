from .copywriter import CopywriterAgent
from .designer import DesignerAgent
from .publisher import PublisherAgent
from .quality import ContentQualityGuard
from .schemas import BriefInput
from .strategist import ContentStrategistAgent


class MarketingPipeline:
    def __init__(self) -> None:
        self.strategist = ContentStrategistAgent()
        self.copywriter = CopywriterAgent()
        self.designer = DesignerAgent()
        self.publisher = PublisherAgent()
        self.quality_guard = ContentQualityGuard()

    def run(
        self,
        brief: BriefInput,
        *,
        publish: bool,
        idempotency_key: str | None = None,
    ) -> dict:
        strategy = self.strategist.run(brief)
        copy = self.copywriter.run(strategy)
        design = self.designer.run(brief, copy)
        quality = self.quality_guard.validate(copy.copy_final, brief.tono_marca)

        publish_result = None
        if publish and quality.approved:
            publish_result = self.publisher.run(
                brief.red_social,
                copy,
                design,
                idempotency_key=idempotency_key,
            )

        return {
            "strategy": strategy.model_dump(),
            "copy": copy.model_dump(),
            "design": design.model_dump(),
            "quality": quality.model_dump(),
            "publish_result": publish_result.model_dump() if publish_result else None,
        }
