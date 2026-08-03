"""Agente diseñador de video: guion -> fondos por escena -> voz en off única -> Timeline -> render (Reels)."""

from __future__ import annotations

import structlog

from .image_providers import generate_image
from .schemas import BriefInput, CopyOutput, StrategyOutput, VideoDesignOutput
from .video_providers import render_video
from .video_script import VideoScriptAgent
from .video_timeline import Scene, Timeline, VoiceoverTrack
from .voice_providers import synthesize_voice

logger = structlog.get_logger(__name__)


def _parse_duration_seconds(duration: str, default: float = 5.0) -> float:
    """Convierte '5s' / '10s' de Venice a float segundos."""
    text = (duration or "").strip().lower().rstrip("s")
    try:
        value = float(text)
        return value if value > 0 else default
    except ValueError:
        return default


def _animate_scene_with_venice(
    background_url: str,
    *,
    visual_prompt: str,
    settings,
) -> tuple[str, float]:
    """Image-to-video Venice: still → MP4 local. Devuelve (url, duration_s)."""
    from .venice_client import (
        generate_video_bytes,
        image_url_to_data_uri,
        save_video_bytes,
        venice_aspect_ratio,
    )

    motion_prompt = (
        f"Subtle cinematic camera motion for a social ad. "
        f"Scene: {visual_prompt[:800]}. Smooth, professional, no text overlay."
    )
    data_uri = image_url_to_data_uri(background_url)
    duration_s = _parse_duration_seconds(settings.venice_video_duration, 5.0)
    raw = generate_video_bytes(
        motion_prompt,
        api_key=settings.venice_api_key,
        base_url=settings.venice_api_base,
        model=settings.venice_video_model,
        duration=settings.venice_video_duration or "5s",
        resolution=settings.venice_video_resolution or "720p",
        aspect_ratio=venice_aspect_ratio(1080, 1920),
        image_url=data_uri,
        max_wait_seconds=settings.video_max_wait_seconds,
    )
    video_url = save_video_bytes(raw, prefix="venice_scene")
    logger.info("video_designer.venice_scene_ok", url=video_url, duration_s=duration_s)
    return video_url, duration_s


class VideoDesignerAgent:
    """Genera un Reel completo: guion, fondos por escena, voz en off y render final vía provider switch."""

    def __init__(self, *, script_agent: VideoScriptAgent | None = None) -> None:
        """Permite inyectar un `VideoScriptAgent` propio (tests); por defecto instancia el real."""
        self.script_agent = script_agent or VideoScriptAgent()

    def run(
        self,
        brief: BriefInput,
        copy: CopyOutput,
        strategy: StrategyOutput,
        *,
        image_provider: str | None = None,
        voice_provider: str | None = None,
        video_provider: str | None = None,
        revision_notes: str | None = None,
    ) -> VideoDesignOutput:
        """Ejecuta guion -> fondos -> voz off -> Timeline -> render; devuelve `VideoDesignOutput`."""
        from gateway.app.core.settings import get_settings

        s = get_settings()
        script = self.script_agent.run(brief, strategy, copy, revision_notes=revision_notes)
        scene_provider = (s.video_scene_provider or "still").strip().lower()
        animate = scene_provider == "venice" and bool(s.venice_api_key.strip())
        if scene_provider == "venice" and not s.venice_api_key.strip():
            logger.warning(
                "video_designer.venice_scene_skipped",
                reason="VIDEO_SCENE_PROVIDER=venice but VENICE_API_KEY empty",
            )

        scenes: list[Scene] = []
        brand_text = (getattr(brief, "brand_context", "") or "").strip()
        brand_prefix = ""
        if brand_text:
            from .brand_visual import brand_priority_prompt_block, parse_brand_visual_cues

            cues = parse_brand_visual_cues(brand_text)
            brand_prefix = brand_priority_prompt_block(cues, brand_text) + " "

        for scene in script.scenes:
            visual = f"{brand_prefix}{scene.visual_prompt}".strip()
            background_url, _, _ = generate_image(
                visual,
                image_provider=image_provider,
                red_social=brief.red_social,
                content_format="reel",
            )
            asset_type = "image"
            duration_s = 4.0
            if animate:
                try:
                    background_url, duration_s = _animate_scene_with_venice(
                        background_url,
                        visual_prompt=scene.visual_prompt,
                        settings=s,
                    )
                    asset_type = "video"
                except Exception as exc:
                    # Degradación: Ken Burns sobre el still (no tumba el reel entero).
                    logger.warning(
                        "video_designer.venice_scene_degraded",
                        error=str(exc),
                        fallback="still_image",
                    )
                    asset_type = "image"
                    duration_s = 4.0

            scenes.append(
                Scene(
                    background_url=background_url,
                    headline=scene.headline,
                    subline=scene.subline,
                    narration=scene.narration,
                    duration_s=duration_s,
                    asset_type=asset_type,  # type: ignore[arg-type]
                    effect="" if asset_type == "video" else "zoomIn",
                )
            )

        # Voz en off única para todo el reel (v1: audio solo narración, sin música).
        narration_text = " ".join(scene.narration for scene in script.scenes)
        audio_url, voiceover_duration_s = synthesize_voice(narration_text, voice_provider=voice_provider)

        # Subtítulos: se derivan en to_shotstack_edit desde scene.narration si captions=[]
        timeline = Timeline(
            scenes=scenes,
            voiceover=VoiceoverTrack(audio_url=audio_url, duration_s=voiceover_duration_s),
            captions=[],
        )

        video_url, width, height = render_video(timeline, render_provider=video_provider)

        logger.info(
            "video_designer.done",
            video_url=video_url,
            scene_count=len(scenes),
            duration_s=voiceover_duration_s,
            scene_provider=scene_provider if animate else "still",
        )

        return VideoDesignOutput(
            image_url=None,
            video_url=video_url,
            video_prompt=script.hook,
            video_provider=(video_provider or s.video_provider),
            voice_provider=(voice_provider or s.voice_provider),
            width=width,
            height=height,
            duration_s=voiceover_duration_s,
            scene_count=len(scenes),
            layout_archetype="typographic_poster",
        )
