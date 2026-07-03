"""Agente diseñador de video: guion -> fondos fal.ai por escena -> voz en off única -> Timeline -> render (Reels)."""

from __future__ import annotations

import structlog

from .image_providers import generate_image
from .schemas import BriefInput, CopyOutput, StrategyOutput, VideoDesignOutput
from .video_providers import render_video
from .video_script import VideoScriptAgent
from .video_timeline import Scene, Timeline, VoiceoverTrack
from .voice_providers import synthesize_voice

logger = structlog.get_logger(__name__)


class VideoDesignerAgent:
    """Genera un Reel completo: guion, fondos fal.ai por escena, voz en off y render final vía provider switch."""

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
    ) -> VideoDesignOutput:
        """Ejecuta guion -> fondos -> voz off -> Timeline -> render; devuelve `VideoDesignOutput`."""
        from gateway.app.core.settings import get_settings

        script = self.script_agent.run(brief, strategy, copy)

        scenes: list[Scene] = []
        for scene in script.scenes:
            background_url, _, _ = generate_image(
                scene.visual_prompt,
                image_provider=image_provider,
                red_social=brief.red_social,
                content_format="reel",
            )
            scenes.append(
                Scene(
                    background_url=background_url,
                    headline=scene.headline,
                    subline=scene.subline,
                )
            )

        # Voz en off única para todo el reel (v1: audio solo narración, sin música).
        narration_text = " ".join(scene.narration for scene in script.scenes)
        audio_url, voiceover_duration_s = synthesize_voice(narration_text, voice_provider=voice_provider)

        timeline = Timeline(
            scenes=scenes,
            voiceover=VoiceoverTrack(audio_url=audio_url, duration_s=voiceover_duration_s),
        )

        video_url, width, height = render_video(timeline, render_provider=video_provider)

        s = get_settings()
        logger.info(
            "video_designer.done",
            video_url=video_url,
            scene_count=len(scenes),
            duration_s=voiceover_duration_s,
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
