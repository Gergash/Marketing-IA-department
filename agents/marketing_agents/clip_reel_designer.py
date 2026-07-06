"""ClipReelDesigner: Drive -> clips -> transcripcion -> seleccion hook-scored -> Timeline -> render (user_clip_reel).

Orquesta el flujo completo de "reel con clips del usuario", sibling de `VideoDesignerAgent`
(que genera fondos con IA). Reutiliza el mismo `Timeline`/`render_video` provider-neutral;
la unica diferencia estructural es que las escenas son `asset_type="video"` recortadas de
clips reales en vez de imagenes generadas.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from .clip_assets import clip_public_url
from .clip_editor import _MAX_CLIP_S, _MIN_CLIP_S, ClipEditorAgent, SelectedSegment
from .drive_source import list_and_download_clips
from .schemas import BriefInput, CopyOutput, StrategyOutput, VideoDesignOutput
from .transcription_providers import transcribe_clips
from .video_providers import render_video
from .video_timeline import Caption, Scene, Timeline

logger = structlog.get_logger(__name__)


def _validate_duration_band(total_duration_s: float) -> None:
    """Banda 6-60s exclusiva de user_clip_reel (nunca la banda 15-30s del reel generado)."""
    if not (_MIN_CLIP_S <= total_duration_s <= _MAX_CLIP_S):
        raise RuntimeError(
            f"user_clip_reel duration out of band: {total_duration_s:.1f}s "
            f"(expected {_MIN_CLIP_S:.0f}-{_MAX_CLIP_S:.0f}s)"
        )


def _apply_wan_effect(video_url: str, prompt: str, api_key: str, model: str) -> str:
    """Aplica fal.ai wan-effects sobre el video del segmento hook; degrada a la url original si falla."""
    import os

    os.environ.setdefault("FAL_KEY", api_key)

    try:
        import fal_client
    except ImportError:
        logger.error("clip_reel.fal_missing_sdk", hint="pip install fal-client")
        return video_url

    try:
        result = fal_client.run(
            model,
            arguments={"video_url": video_url, "prompt": prompt[:2000]},
        )
        out_url: str = result["video"]["url"]
        logger.info("clip_reel.wan_effect_ok", model=model)
        return out_url
    except Exception as exc:
        logger.warning("clip_reel.wan_effect_failed", error=str(exc))
        return video_url


class ClipReelDesigner:
    """Genera un `user_clip_reel` completo desde una carpeta de Drive del usuario."""

    def __init__(self, *, editor_agent: ClipEditorAgent | None = None) -> None:
        """Permite inyectar un `ClipEditorAgent` propio (tests); por defecto instancia el real."""
        self.editor_agent = editor_agent or ClipEditorAgent()

    def run(
        self,
        brief: BriefInput,
        copy: CopyOutput,
        strategy: StrategyOutput,
        *,
        db: Session,
        tenant_id: str,
        run_id: int,
        drive_folder_id: str,
        video_provider: str | None = None,
    ) -> VideoDesignOutput:
        """Ejecuta drive -> transcripcion -> seleccion -> [efecto opcional] -> Timeline -> render."""
        from gateway.app.core.settings import get_settings

        s = get_settings()

        downloaded = list_and_download_clips(db, tenant_id, drive_folder_id, run_id)
        clip_paths = [(clip.clip_id, Path(clip.path)) for clip in downloaded]
        clip_url_by_id = {clip.clip_id: clip_public_url(clip.path) for clip in downloaded}

        transcripts = transcribe_clips(clip_paths, stt_provider=s.stt_provider)
        segments: list[SelectedSegment] = self.editor_agent.run(transcripts, brief, strategy)

        total_duration_s = sum(seg.end_s - seg.start_s for seg in segments)
        _validate_duration_band(total_duration_s)

        scenes: list[Scene] = []
        captions: list[Caption] = []
        timeline_cursor = 0.0
        for seg in segments:
            source_url = clip_url_by_id.get(seg.clip_id, "")
            duration_s = seg.end_s - seg.start_s
            trim_in = seg.start_s
            trim_out: float | None = seg.end_s

            if seg.is_hook and s.effects_enabled and s.fal_api_key:
                effect_url = _apply_wan_effect(
                    source_url,
                    strategy.hook,
                    s.fal_api_key,
                    s.fal_effects_model,
                )
                if effect_url != source_url:
                    # El output de wan-effects YA es el segmento recortado (no el clip fuente
                    # completo): el trim original ya no aplica y debe resetearse, o Shotstack
                    # recortaria fuera de rango sobre el archivo equivocado.
                    trim_in = 0.0
                    trim_out = duration_s
                source_url = effect_url

            scenes.append(
                Scene(
                    background_url=source_url or seg.clip_id,
                    headline=strategy.hook if seg.is_hook else "",
                    asset_type="video",
                    trim_in=trim_in,
                    trim_out=trim_out,
                    duration_s=duration_s,
                )
            )
            if seg.text:
                captions.append(Caption(text=seg.text, start_s=timeline_cursor, end_s=timeline_cursor + duration_s))
            timeline_cursor += duration_s

        timeline = Timeline(scenes=scenes, captions=captions)
        video_url, width, height = render_video(timeline, render_provider=video_provider)

        logger.info(
            "clip_reel_designer.done",
            video_url=video_url,
            scene_count=len(scenes),
            duration_s=total_duration_s,
        )

        return VideoDesignOutput(
            image_url=None,
            video_url=video_url,
            video_prompt=strategy.hook,
            video_provider=(video_provider or s.video_provider),
            voice_provider="",
            width=width,
            height=height,
            duration_s=total_duration_s,
            scene_count=len(scenes),
            layout_archetype="typographic_poster",
        )
