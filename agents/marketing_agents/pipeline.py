"""Pipeline principal: orquestación lineal + subgrafo LangGraph copy/QA."""

from .caption import build_publish_caption
from .clip_reel_designer import ClipReelDesigner
from .copywriter import CopywriterAgent
from .designer import DesignerAgent
from .graph_copy_qa import build_copy_qa_graph, invoke_copy_qa
from .publisher import PublisherAgent
from .quality import ContentQualityGuard
from .schemas import BriefInput
from .strategist import ContentStrategistAgent
from .thought_stream import (
    CHECKPOINT_COPY,
    CHECKPOINT_DESIGN,
    CHECKPOINT_STRATEGY,
    NullThoughtStream,
)
from .video_designer import VideoDesignerAgent

# content_format que usan el render de video (Timeline -> Shotstack) en vez de imagen estatica.
_VIDEO_CONTENT_FORMATS = frozenset({"reel", "user_clip_reel"})

# Tope de idas y vueltas por checkpoint: evita que un usuario indeciso deje el run colgado.
_MAX_CHECKPOINT_ROUNDS = 3


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
        link_url: str | None = None,
        cta_on_image: bool = False,
        thoughts=None,
        video_gen_mode: str | None = None,
        venice_video_model: str | None = None,
    ) -> dict:
        """Ejecuta estratega → grafo copy/QA → diseño → publicación opcional; devuelve dict serializable.

        `thoughts` narra cada paso al dashboard y, en modo interactivo, abre los
        checkpoints donde el usuario puede redirigir a los agentes.
        """
        thoughts = thoughts or NullThoughtStream()
        thoughts.emit(
            "pipeline",
            "start",
            f"Arranca el equipo para «{brief.tema}» en {brief.red_social} ({content_format}).",
            data={
                "content_format": content_format,
                "objetivo": brief.objetivo,
                "publico_objetivo": brief.publico_objetivo,
                "brand_manual": bool(brief.brand_context),
            },
        )

        strategy = self._run_strategy(brief, thoughts)
        copy, quality, copy_qa_trace = self._run_copy_qa(brief, strategy, thoughts)

        # Descripción publicable: cuerpo + link opcional + hashtags (nunca como botón en imagen).
        copy.copy_final = build_publish_caption(
            copy.copy_final,
            copy.hashtags,
            link_url=link_url,
        )

        # Última parada antes de gastar créditos de imagen/video: el usuario puede añadir
        # indicaciones visuales sobre el copy que acaba de leer.
        decision = thoughts.ask(
            "designer",
            CHECKPOINT_DESIGN,
            "Voy a producir la pieza visual. ¿Alguna indicación de arte antes de generar?",
            draft={
                "content_format": content_format,
                "headline": copy.headline_for_image,
                "subline": copy.subline_for_image,
                "archetype_override": archetype_override or "",
                "visual_instructions": visual_instructions or "",
            },
        )
        if decision["action"] == "adjust":
            visual_instructions = _merge_notes(visual_instructions, decision["notes"])
            revision_notes = _merge_notes(revision_notes, decision["notes"])

        if content_format == "user_clip_reel":
            # Branch de clips del usuario: Drive -> transcripcion -> seleccion hook-scored -> Timeline -> render.
            thoughts.think(
                "clip_reel_designer",
                "Descargando tus clips de Drive, transcribiendo y eligiendo los mejores momentos…",
                drive_folder_id=drive_folder_id or "",
            )
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
            _emit_video_output(thoughts, "clip_reel_designer", design)
        elif content_format == "reel":
            # Branch de video generado: guion -> fondos fal.ai -> voz off -> Timeline -> render (Shotstack).
            thoughts.think(
                "video_designer",
                "Escribiendo el guion, generando escenas y la voz en off; el render tarda unos minutos…",
                image_provider=image_provider or "",
            )
            design = self.video_designer.run(
                brief,
                copy,
                strategy,
                image_provider=image_provider,
                revision_notes=revision_notes,
                video_gen_mode=video_gen_mode,
                venice_video_model=venice_video_model,
            )
            _emit_video_output(thoughts, "video_designer", design)
        else:
            thoughts.think(
                "designer",
                "Eligiendo arquetipo, generando la imagen y componiendo la tipografía…",
                image_provider=image_provider or "",
                archetype_override=archetype_override or "",
                user_asset=bool(user_asset_url),
            )
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
                cta_on_image=cta_on_image,
                tenant_id=tenant_id,
            )
            thoughts.output(
                "designer",
                f"Pieza lista con el layout «{design.layout_label or design.layout_archetype}».",
                image_url=design.image_url,
                layout_archetype=design.layout_archetype,
                layout_label=design.layout_label,
                image_provider=design.image_provider,
                width=design.image_width,
                height=design.image_height,
                design_source=design.design_source,
            )

        publish_result = None
        # PublisherAgent/social_providers aún no son video-aware (image_url requerido);
        # la publicación de reels (generados o de clips del usuario) ocurre vía Go sidecar
        # (result["design"]["video_url"]), no aquí.
        if publish and quality.approved and content_format not in _VIDEO_CONTENT_FORMATS:
            thoughts.think("publisher", f"Publicando en {brief.red_social}…")
            publish_result = self.publisher.run(
                brief.red_social,
                copy,
                design,
                idempotency_key=idempotency_key,
                content_format=content_format,
            )
            thoughts.output(
                "publisher",
                f"Publicado: {publish_result.publication_url or publish_result.status}",
                status=publish_result.status,
                publication_url=publish_result.publication_url,
            )

        thoughts.emit(
            "pipeline",
            "end",
            "Pieza terminada; queda a la espera de tu revisión."
            if quality.approved
            else "Pieza terminada, pero QA no la aprobó: revísala antes de publicar.",
            data={"quality_approved": quality.approved},
        )

        return {
            "strategy": strategy.model_dump(),
            "copy": copy.model_dump(),
            "design": design.model_dump(),
            "quality": quality.model_dump(),
            "copy_qa_trace": copy_qa_trace,
            "publish_result": publish_result.model_dump() if publish_result else None,
        }

    # ------------------------------------------------------------------
    # Tramos con checkpoint
    # ------------------------------------------------------------------

    def _run_strategy(self, brief: BriefInput, thoughts):
        """Estrategia + checkpoint: el usuario puede reorientarla antes de que se escriba una línea."""
        notes = ""
        for _ in range(_MAX_CHECKPOINT_ROUNDS):
            thoughts.think(
                "strategist",
                "Leyendo el brief y el manual de marca para decidir ángulo, hook y tipo de post…",
            )
            strategy = self.strategist.run(brief, user_notes=notes or None)
            thoughts.output(
                "strategist",
                f"Propongo un post {strategy.tipo_post} con el hook: «{strategy.hook}»",
                tipo_post=strategy.tipo_post,
                hook=strategy.hook,
                mensaje_base=strategy.mensaje_base,
                hashtags=list(strategy.hashtags),
            )
            decision = thoughts.ask(
                "strategist",
                CHECKPOINT_STRATEGY,
                "¿Vamos con este ángulo o prefieres otro enfoque?",
                draft=strategy.model_dump(),
            )
            if decision["action"] != "adjust":
                return strategy
            notes = decision["notes"]
        return strategy

    def _run_copy_qa(self, brief: BriefInput, strategy, thoughts):
        """Bucle copy/QA + checkpoint: el usuario ajusta el texto antes de producir la pieza."""
        notes = ""
        for _ in range(_MAX_CHECKPOINT_ROUNDS):
            gout = invoke_copy_qa(
                self._copy_qa_graph,
                brief=brief,
                strategy=strategy,
                max_attempts=self._max_copy_qa_attempts,
                user_notes=notes,
                thoughts=thoughts,
            )
            copy = gout["copy"]
            quality = gout["quality"]
            trace = list(gout.get("events", []))
            decision = thoughts.ask(
                "copywriter",
                CHECKPOINT_COPY,
                "¿Te sirve este copy o quieres que lo reescriba con tus notas?",
                draft=copy.model_dump(),
            )
            if decision["action"] != "adjust":
                return copy, quality, trace
            notes = decision["notes"]
        return copy, quality, trace


def _merge_notes(existing: str | None, extra: str) -> str:
    """Concatena las notas del checkpoint con las que ya traía el run, sin perder ninguna."""
    parts = [p.strip() for p in (existing or "", extra) if p and p.strip()]
    return ". ".join(parts)


def _emit_video_output(thoughts, agent: str, design) -> None:
    """Publica el resultado de los diseñadores de video, que comparten `VideoDesignOutput`."""
    thoughts.output(
        agent,
        f"Video renderizado ({design.scene_count} escenas, {design.duration_s:.1f}s).",
        video_url=design.video_url,
        video_provider=design.video_provider,
        duration_s=design.duration_s,
        scene_count=design.scene_count,
    )
