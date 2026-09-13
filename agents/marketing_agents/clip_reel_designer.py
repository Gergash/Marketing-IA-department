"""ClipReelDesigner: Drive cloud (audio-only) → VideoProducer → pending_takes → cut shorts → Shotstack.

No descarga el máster completo: analiza audio en stream, propone N tomas, y solo al render
materializa MP4 cortos desde Drive.
"""

from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

from .cloud_footage import (
    get_drive_access_token,
    list_cloud_footage,
    materialize_accepted_shorts,
    transcribe_cloud_footage,
)
from .schemas import (
    BriefInput,
    CopyOutput,
    ManualTakeRange,
    StrategyOutput,
    TakeProposal,
    VideoDesignOutput,
)
from .video_producer import VideoProducerAgent, _MAX_TOTAL_S
from .video_providers import render_video
from .video_timeline import Caption, Scene, Timeline

logger = structlog.get_logger(__name__)

_MIN_TOTAL_S = 6.0


def _validate_duration_band(total_duration_s: float) -> None:
    """Banda 6–90s para user_clip_reel cloud (N tomas cortas)."""
    if not (_MIN_TOTAL_S <= total_duration_s <= _MAX_TOTAL_S):
        raise RuntimeError(
            f"user_clip_reel duration out of band: {total_duration_s:.1f}s "
            f"(expected {_MIN_TOTAL_S:.0f}-{_MAX_TOTAL_S:.0f}s)"
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


def accepted_takes_sorted(takes: list[TakeProposal]) -> list[TakeProposal]:
    """Filtra tomas accepted y las ordena por `order`."""
    return sorted(
        [t for t in takes if t.status == "accepted"],
        key=lambda t: t.order,
    )


class ClipReelDesigner:
    """Propone tomas desde Drive (cloud) y renderiza el reel solo con las aceptadas."""

    def __init__(self, *, producer_agent: VideoProducerAgent | None = None) -> None:
        self.producer_agent = producer_agent or VideoProducerAgent()

    def propose(
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
        revision_notes: str | None = None,
        editing_goal: str | None = None,
        take_count: int = 10,
        selection_mode: str = "auto",
        manual_ranges: list[dict] | list[ManualTakeRange] | None = None,
    ) -> VideoDesignOutput:
        """Audio-only STT + VideoProducer → takes[] sin Shotstack ni máster local."""
        from gateway.app.core.settings import get_settings

        s = get_settings()
        footage = list_cloud_footage(db, tenant_id, drive_folder_id)
        access_token = get_drive_access_token(db, tenant_id)
        transcripts = transcribe_cloud_footage(footage, access_token, stt_provider=s.stt_provider)

        footage_by_clip = {f.clip_id: f.file_id for f in footage}
        ranges: list[ManualTakeRange] = []
        for item in manual_ranges or []:
            if isinstance(item, ManualTakeRange):
                ranges.append(item)
            else:
                ranges.append(ManualTakeRange(**item))

        takes = self.producer_agent.run(
            transcripts,
            brief,
            strategy,
            footage_by_clip=footage_by_clip,
            take_count=int(take_count or 10),
            selection_mode=selection_mode or "auto",
            editing_goal=editing_goal,
            manual_ranges=ranges,
            revision_notes=revision_notes,
        )

        total_duration_s = sum(t.duration_s for t in takes)
        _validate_duration_band(total_duration_s)

        logger.info(
            "clip_reel_designer.proposed",
            take_count=len(takes),
            duration_s=total_duration_s,
            mode=selection_mode,
        )

        return VideoDesignOutput(
            image_url=None,
            video_url="",
            video_prompt=strategy.hook,
            video_provider=(video_provider or s.video_provider),
            voice_provider="",
            width=0,
            height=0,
            duration_s=total_duration_s,
            scene_count=len(takes),
            layout_archetype="typographic_poster",
            takes=takes,
            footage=footage,
        )

    def render_from_takes(
        self,
        takes: list[TakeProposal],
        *,
        strategy_hook: str,
        video_provider: str | None = None,
        db: Session | None = None,
        tenant_id: str | None = None,
        run_id: int | None = None,
    ) -> VideoDesignOutput:
        """Corta shorts desde Drive si hace falta, arma Timeline + Shotstack."""
        from gateway.app.core.settings import get_settings

        s = get_settings()
        accepted = accepted_takes_sorted(takes)
        if not accepted:
            raise RuntimeError("no accepted takes to render")

        total_duration_s = sum(t.duration_s for t in accepted)
        _validate_duration_band(total_duration_s)

        short_urls: dict[str, str] = {}
        if db is not None and tenant_id and run_id is not None:
            short_urls = materialize_accepted_shorts(db, tenant_id, run_id, accepted)

        scenes: list[Scene] = []
        captions: list[Caption] = []
        timeline_cursor = 0.0
        for take in accepted:
            source_url = short_urls.get(take.id) or take.source_clip_url
            duration_s = take.duration_s
            # Tras materializar el short, el archivo ya empieza en 0.
            trim_in = 0.0 if take.id in short_urls else take.trim_in
            trim_out: float | None = duration_s if take.id in short_urls else take.trim_out

            if take.is_hook and s.effects_enabled and s.fal_api_key:
                effect_url = _apply_wan_effect(
                    source_url,
                    strategy_hook,
                    s.fal_api_key,
                    s.fal_effects_model,
                )
                if effect_url != source_url:
                    trim_in = 0.0
                    trim_out = duration_s
                source_url = effect_url

            scenes.append(
                Scene(
                    background_url=source_url or take.clip_id,
                    headline=strategy_hook if take.is_hook else "",
                    asset_type="video",
                    trim_in=trim_in,
                    trim_out=trim_out,
                    duration_s=duration_s,
                )
            )
            if take.transcript:
                captions.append(
                    Caption(
                        text=take.transcript,
                        start_s=timeline_cursor,
                        end_s=timeline_cursor + duration_s,
                    )
                )
            timeline_cursor += duration_s

        timeline = Timeline(scenes=scenes, captions=captions)
        video_url, width, height = render_video(timeline, render_provider=video_provider)

        logger.info(
            "clip_reel_designer.rendered",
            video_url=video_url,
            scene_count=len(scenes),
            duration_s=total_duration_s,
        )

        # Actualiza URLs de tomas accepted con shorts materializados
        updated = []
        for t in takes:
            if t.id in short_urls:
                updated.append(
                    t.model_copy(
                        update={
                            "source_clip_url": short_urls[t.id],
                            "trim_in": 0.0,
                            "trim_out": t.duration_s,
                        }
                    )
                )
            else:
                updated.append(t)

        return VideoDesignOutput(
            image_url=None,
            video_url=video_url,
            video_prompt=strategy_hook,
            video_provider=(video_provider or s.video_provider),
            voice_provider="",
            width=width,
            height=height,
            duration_s=total_duration_s,
            scene_count=len(scenes),
            layout_archetype="typographic_poster",
            takes=updated,
        )

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
        revision_notes: str | None = None,
        editing_goal: str | None = None,
        take_count: int = 10,
        selection_mode: str = "auto",
        manual_ranges: list[dict] | None = None,
    ) -> VideoDesignOutput:
        """Alias de `propose` para el pipeline."""
        return self.propose(
            brief,
            copy,
            strategy,
            db=db,
            tenant_id=tenant_id,
            run_id=run_id,
            drive_folder_id=drive_folder_id,
            video_provider=video_provider,
            revision_notes=revision_notes,
            editing_goal=editing_goal,
            take_count=take_count,
            selection_mode=selection_mode,
            manual_ranges=manual_ranges,
        )
