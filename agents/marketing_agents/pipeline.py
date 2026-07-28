"""Pipeline principal: orquestación lineal + subgrafo LangGraph copy/QA."""

from .clip_reel_designer import ClipReelDesigner
from .copywriter import CopywriterAgent
from .designer import DesignerAgent
from .graph_copy_qa import build_copy_qa_graph, invoke_copy_qa
from .publisher import PublisherAgent
from .quality import ContentQualityGuard
from .schemas import BriefInput
from .strategist import ContentStrategistAgent
from .video_designer import VideoDesignerAgent

# content_format que usan el render de video (Timeline -> Shotstack) en vez de imagen estatica.
_VIDEO_CONTENT_FORMATS = frozenset({"reel", "user_clip_reel"})


class MarketingPipeline:
    """Orquestación híbrida: tramo lineal en Python + bucle Copy/QA en LangGraph."""

    def __init__(self, *, max_copy_qa_attempts: int = 3) -> None:
        """Instancia agentes y compila una vez el subgrafo LangGraph copy/QA con el tope de reintentos dado."""
        self.strategist = ContentStrategistAgent()
        self.copywriter = CopywriterAgent()
        self.designer = DesignerAgent()
        self.video_designer = VideoDesignerAgent()
        self.clip_reel_designer = ClipReelDesigner()
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
        user_asset_url: str | None = None,
        alter_image_with_ai: bool = False,
        visual_instructions: str | None = None,
        db=None,
        tenant_id: str | None = None,
        run_id: int | None = None,
        drive_folder_id: str | None = None,
        revision_notes: str | None = None,
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

        if content_format == "user_clip_reel":
            # Branch de clips del usuario: Drive -> transcripcion -> seleccion hook-scored -> Timeline -> render.
            design = self.clip_reel_designer.run(
                brief,
                copy,
                strategy,
                db=db,
                tenant_id=tenant_id,
                run_id=run_id,
                drive_folder_id=drive_folder_id,
                revision_notes=revision_notes,
            )
        elif content_format == "reel":
            # Branch de video generado: guion -> fondos fal.ai -> voz off -> Timeline -> render (Shotstack).
            design = self.video_designer.run(
                brief,
                copy,
                strategy,
                image_provider=image_provider,
                revision_notes=revision_notes,
            )
        else:
            design = self.designer.run(
                brief,
                copy,
                strategy,
                image_provider=image_provider,
                content_format=content_format,
                archetype_override=archetype_override,
                user_asset_url=user_asset_url,
                alter_image_with_ai=alter_image_with_ai,
                visual_instructions=visual_instructions,
                revision_notes=revision_notes,
            )

        publish_result = None
        # PublisherAgent/social_providers aún no son video-aware (image_url requerido);
        # la publicación de reels (generados o de clips del usuario) ocurre vía Go sidecar
        # (result["design"]["video_url"]), no aquí.
        if publish and quality.approved and content_format not in _VIDEO_CONTENT_FORMATS:
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
