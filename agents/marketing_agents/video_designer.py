"""Agente diseñador de video: guion -> Venice AI y/o Shotstack -> Timeline -> render (Reels).

Modos (`video_gen_mode`):
- full   → un solo clip generado por Venice (Seedance / Kling O3 / MiniMax), sin collage de stills
- scenes → una toma AI por escena (Venice i2v/t2v) y luego unir con Shotstack
- still  → stills + Ken Burns en Shotstack (legacy / sin clave Venice)
"""

from __future__ import annotations

import structlog

from .image_providers import generate_image
from .schemas import BriefInput, CopyOutput, StrategyOutput, VideoDesignOutput
from .venice_video_models import resolve_venice_video_model
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


def _resolve_mode(settings, *, video_gen_mode: str | None) -> str:
    raw = (video_gen_mode or getattr(settings, "video_gen_mode", None) or "scenes").strip().lower()
    if raw in {"full", "ai_full", "clip", "single"}:
        return "full"
    if raw in {"scenes", "stitch", "takes", "unir"}:
        return "scenes"
    if raw in {"still", "shotstack", "stills"}:
        return "still"
    # Compat: VIDEO_SCENE_PROVIDER=venice sin mode → scenes
    scene_p = (getattr(settings, "video_scene_provider", "") or "").strip().lower()
    if scene_p == "venice":
        return "scenes"
    return "still"


def _model_alias(settings, *, venice_video_model: str | None) -> str:
    return (
        (venice_video_model or getattr(settings, "venice_video_model", "") or "seedance-2.0")
        .strip()
    )


def _animate_with_venice(
    *,
    prompt: str,
    settings,
    model_alias: str,
    image_url: str | None = None,
    prefix: str = "venice_scene",
) -> tuple[str, float]:
    """Genera MP4 vía Venice queue. Devuelve (url, duration_s)."""
    from .venice_client import (
        generate_video_bytes,
        image_url_to_data_uri,
        save_video_bytes,
        venice_aspect_ratio,
    )

    for_image = bool(image_url)
    model = resolve_venice_video_model(model_alias, for_image=for_image)
    data_uri = image_url_to_data_uri(image_url) if image_url else None
    duration_s = _parse_duration_seconds(settings.venice_video_duration, 5.0)
    aspect = venice_aspect_ratio(1080, 1920) if not for_image else None
    raw = generate_video_bytes(
        prompt[:2400],
        api_key=settings.venice_api_key,
        base_url=settings.venice_api_base,
        model=model,
        duration=settings.venice_video_duration or "5s",
        resolution=settings.venice_video_resolution or "720p",
        aspect_ratio=aspect,
        image_url=data_uri,
        max_wait_seconds=settings.video_max_wait_seconds,
    )
    video_url = save_video_bytes(raw, prefix=prefix)
    logger.info(
        "video_designer.venice_ok",
        url=video_url,
        duration_s=duration_s,
        model=model,
        has_image=for_image,
    )
    return video_url, duration_s


def _build_full_ai_prompt(
    *,
    brief: BriefInput,
    copy: CopyOutput,
    script,
    brand_prefix: str,
) -> str:
    beats = " | ".join(
        f"{i + 1}. {sc.visual_prompt[:180]}" for i, sc in enumerate(script.scenes[:5])
    )
    headline = (copy.headline or brief.tema or "").strip()
    return (
        f"{brand_prefix}"
        f"Vertical 9:16 Instagram Reel, cinematic social ad. "
        f"Brand topic: {brief.tema}. Tone: {brief.tono_marca}. "
        f"Hook: {script.hook}. Headline: {headline}. "
        f"Sequence beats: {beats}. "
        f"Smooth camera, professional lighting, no on-screen text, no watermarks."
    )


class VideoDesignerAgent:
    """Genera un Reel completo: guion, fondos/tomas AI, voz en off y render final."""

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
        video_gen_mode: str | None = None,
        venice_video_model: str | None = None,
    ) -> VideoDesignOutput:
        """Ejecuta guion -> video AI / stills -> voz off -> Timeline -> render."""
        from gateway.app.core.settings import get_settings

        s = get_settings()
        script = self.script_agent.run(brief, strategy, copy, revision_notes=revision_notes)
        mode = _resolve_mode(s, video_gen_mode=video_gen_mode)
        model_alias = _model_alias(s, venice_video_model=venice_video_model)
        has_venice = bool(s.venice_api_key.strip())

        if mode in {"full", "scenes"} and not has_venice:
            logger.warning(
                "video_designer.venice_missing_key",
                mode=mode,
                fallback="still",
            )
            mode = "still"

        brand_text = (getattr(brief, "brand_context", "") or "").strip()
        brand_prefix = ""
        if brand_text:
            from .brand_visual import brand_priority_prompt_block, parse_brand_visual_cues

            cues = parse_brand_visual_cues(brand_text)
            brand_prefix = brand_priority_prompt_block(cues, brand_text) + " "

        if mode == "full":
            return self._run_full_ai(
                brief,
                copy,
                strategy,
                script=script,
                brand_prefix=brand_prefix,
                settings=s,
                model_alias=model_alias,
                image_provider=image_provider,
                voice_provider=voice_provider,
                video_provider=video_provider,
            )

        return self._run_scenes_or_still(
            brief,
            copy,
            strategy,
            script=script,
            brand_prefix=brand_prefix,
            settings=s,
            mode=mode,
            model_alias=model_alias,
            image_provider=image_provider,
            voice_provider=voice_provider,
            video_provider=video_provider,
        )

    def _run_full_ai(
        self,
        brief: BriefInput,
        copy: CopyOutput,
        strategy: StrategyOutput,
        *,
        script,
        brand_prefix: str,
        settings,
        model_alias: str,
        image_provider: str | None,
        voice_provider: str | None,
        video_provider: str | None,
    ) -> VideoDesignOutput:
        """Un clip Venice para todo el reel (opcionalmente anclado a un still hero)."""
        _ = strategy
        hero_url = None
        try:
            hero_prompt = (
                f"{brand_prefix}{script.scenes[0].visual_prompt}".strip()
                if script.scenes
                else f"{brand_prefix}{brief.tema} product hero vertical"
            )
            hero_url, _, _ = generate_image(
                hero_prompt,
                image_provider=image_provider,
                red_social=brief.red_social,
                content_format="reel",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("video_designer.full_hero_still_skipped", error=str(exc))

        prompt = _build_full_ai_prompt(
            brief=brief, copy=copy, script=script, brand_prefix=brand_prefix
        )
        try:
            video_url, duration_s = _animate_with_venice(
                prompt=prompt,
                settings=settings,
                model_alias=model_alias,
                image_url=hero_url,
                prefix="venice_full",
            )
        except Exception as exc:
            logger.warning(
                "video_designer.full_ai_failed",
                error=str(exc),
                fallback="scenes",
            )
            return self._run_scenes_or_still(
                brief,
                copy,
                strategy,
                script=script,
                brand_prefix=brand_prefix,
                settings=settings,
                mode="scenes",
                model_alias=model_alias,
                image_provider=image_provider,
                voice_provider=voice_provider,
                video_provider=video_provider,
            )

        narration_text = " ".join(sc.narration for sc in script.scenes) or (copy.headline or brief.tema)
        audio_url, voiceover_duration_s = synthesize_voice(
            narration_text, voice_provider=voice_provider
        )
        # Timeline de una sola toma AI; Shotstack puede muxear audio + subtítulos
        scene = Scene(
            background_url=video_url,
            headline=copy.headline or script.hook,
            subline=(
                getattr(copy, "subline_for_image", None)
                or (script.scenes[0].subline if script.scenes else None)
            ),
            narration=narration_text,
            duration_s=max(duration_s, voiceover_duration_s or duration_s),
            asset_type="video",
            effect="",
        )
        timeline = Timeline(
            scenes=[scene],
            voiceover=VoiceoverTrack(audio_url=audio_url, duration_s=voiceover_duration_s),
            captions=[],
        )
        out_url, width, height = render_video(timeline, render_provider=video_provider)
        logger.info(
            "video_designer.done",
            video_url=out_url,
            scene_count=1,
            mode="full",
            model=model_alias,
        )
        return VideoDesignOutput(
            image_url=hero_url,
            video_url=out_url,
            video_prompt=script.hook,
            video_provider=(video_provider or settings.video_provider),
            voice_provider=(voice_provider or settings.voice_provider),
            width=width,
            height=height,
            duration_s=voiceover_duration_s,
            scene_count=1,
            layout_archetype="typographic_poster",
        )

    def _run_scenes_or_still(
        self,
        brief: BriefInput,
        copy: CopyOutput,
        strategy: StrategyOutput,
        *,
        script,
        brand_prefix: str,
        settings,
        mode: str,
        model_alias: str,
        image_provider: str | None,
        voice_provider: str | None,
        video_provider: str | None,
    ) -> VideoDesignOutput:
        """Por escena: still (+ Venice i2v si mode=scenes) y unir tomas con Shotstack."""
        _ = copy, strategy
        animate = mode == "scenes"
        scenes: list[Scene] = []

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
                    motion = (
                        f"Subtle cinematic camera motion for a social ad. "
                        f"Scene: {scene.visual_prompt[:800]}. Smooth, professional, no text overlay."
                    )
                    background_url, duration_s = _animate_with_venice(
                        prompt=motion,
                        settings=settings,
                        model_alias=model_alias,
                        image_url=background_url,
                        prefix="venice_scene",
                    )
                    asset_type = "video"
                except Exception as exc:
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

        narration_text = " ".join(sc.narration for sc in script.scenes)
        audio_url, voiceover_duration_s = synthesize_voice(
            narration_text, voice_provider=voice_provider
        )
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
            mode=mode,
            model=model_alias if animate else None,
        )
        return VideoDesignOutput(
            image_url=None,
            video_url=video_url,
            video_prompt=script.hook,
            video_provider=(video_provider or settings.video_provider),
            voice_provider=(voice_provider or settings.voice_provider),
            width=width,
            height=height,
            duration_s=voiceover_duration_s,
            scene_count=len(scenes),
            layout_archetype="typographic_poster",
        )
