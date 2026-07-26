"""Contrato JSON provider-neutral para video (Reels): Timeline Pydantic v2 + mapeo a Shotstack.

Este módulo no hace I/O; es el único lugar donde se filtra la forma del JSON de Shotstack.
"""

from __future__ import annotations

from typing import Literal

import structlog
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger(__name__)

# Banda objetivo de duración total del reel (spec: 15-30s) — solo aplica a reels generados,
# NUNCA a user_clip_reel (banda 6-60s vive en clip_reel_designer.py, WU5)
_MIN_TOTAL_DURATION_S = 15.0
_MAX_TOTAL_DURATION_S = 30.0


class Scene(BaseModel):
    """Una escena del reel: fondo fijo (imagen fal.ai) o clip de video (user_clip_reel) + overlay."""

    background_url: str = Field(min_length=1)
    headline: str = ""
    subline: str = ""
    archetype: str = "typographic_poster"  # reutiliza IDs de layout_archetypes para estilo de overlay
    duration_s: float = Field(default=4.0, gt=0)
    effect: str = "zoomIn"  # token provider-neutral (Ken Burns); mapeado a Shotstack en to_shotstack_edit
    asset_type: Literal["image", "video"] = "image"
    # trim_in/trim_out solo tienen sentido para asset_type="video" (clip fuente recortado)
    trim_in: float = 0.0
    trim_out: float | None = None


class Caption(BaseModel):
    """Cue de subtítulo sincronizado a timestamps de palabra (Whisper)."""

    text: str = Field(min_length=1)
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)


class VoiceoverTrack(BaseModel):
    """Pista de voz en off (ElevenLabs/OpenAI TTS) que acompaña las escenas."""

    audio_url: str = Field(min_length=1)
    duration_s: float = Field(gt=0)


class OutputSpec(BaseModel):
    """Especificación de salida del render: vertical 9:16 para Reels."""

    width: int = 1080
    height: int = 1920
    fps: int = 30
    fmt: str = "mp4"


class Timeline(BaseModel):
    """Timeline completo de un reel: 3-5 escenas + voiceover opcional + spec de salida."""

    scenes: list[Scene] = Field(min_length=1)
    voiceover: VoiceoverTrack | None = None
    captions: list[Caption] = Field(default_factory=list)
    output: OutputSpec = Field(default_factory=OutputSpec)

    @field_validator("scenes")
    @classmethod
    def _scenes_have_narration(cls, scenes: list[Scene]) -> list[Scene]:
        """Escenas de imagen deben tener narración (headline/subline); escenas de video no la requieren."""
        for scene in scenes:
            if scene.asset_type == "image" and not (scene.headline or scene.subline):
                raise ValueError("scene missing narration text (headline/subline)")
        return scenes


def _clamped_scene_durations(timeline: Timeline) -> list[float]:
    """Reconcilia duración de escenas con la duración real del voiceover (spec: precedencia clamp/escala).

    - Sin voiceover: usa duration_s de cada escena tal cual.
    - Voiceover > 30s: escala hacia abajo hasta un total de 30s (hard cap, recorta narración excedente).
    - Voiceover < 15s: mantiene las duraciones mínimas de escena (no estira para llenar).
    - Voiceover entre 15s y 30s: escala proporcionalmente a la duración real del voiceover.
    """
    base = [scene.duration_s for scene in timeline.scenes]
    if timeline.voiceover is None:
        return base

    voice_duration = timeline.voiceover.duration_s
    base_total = sum(base)
    if base_total <= 0:
        return base

    if voice_duration > _MAX_TOTAL_DURATION_S:
        logger.warning(
            "video.duration_trimmed",
            voiceover_duration_s=voice_duration,
            hard_cap_s=_MAX_TOTAL_DURATION_S,
        )
        scale = _MAX_TOTAL_DURATION_S / base_total
        return [d * scale for d in base]

    if voice_duration < _MIN_TOTAL_DURATION_S:
        return base

    scale = voice_duration / base_total
    return [d * scale for d in base]


# Estilos TitleAsset válidos en Shotstack (el archetype interno no se envía tal cual).
_SHOTSTACK_TITLE_STYLE = "minimal"


def to_shotstack_edit(timeline: Timeline) -> dict:
    """Mapea el Timeline provider-neutral a la forma de JSON `edit` que espera la API de Shotstack.

    Shotstack exige un Clip por asset: el texto va en pistas overlay (arriba), no como
    propiedad inventada `title_asset` dentro del clip de imagen/video.
    Orden de tracks: captions → títulos → media (el primero se renderiza encima).
    """
    durations = _clamped_scene_durations(timeline)

    media_clips: list[dict] = []
    title_clips: list[dict] = []
    start = 0.0
    for scene, length in zip(timeline.scenes, durations):
        if scene.asset_type == "video":
            media_clips.append(
                {
                    "asset": {"type": "video", "src": scene.background_url, "trim": scene.trim_in},
                    "start": start,
                    "length": length,
                    "fit": "cover",
                }
            )
        else:
            media_clips.append(
                {
                    "asset": {"type": "image", "src": scene.background_url},
                    "start": start,
                    "length": length,
                    "effect": scene.effect,
                    "fit": "cover",
                }
            )

        overlay_text = "\n".join(part for part in (scene.headline, scene.subline) if part).strip()
        if overlay_text:
            title_clips.append(
                {
                    "asset": {
                        "type": "title",
                        "text": overlay_text,
                        "style": _SHOTSTACK_TITLE_STYLE,
                        "color": "#ffffff",
                        "size": "large",
                        "position": "center",
                    },
                    "start": start,
                    "length": length,
                }
            )
        start += length

    # tracks[0] = capa superior. Media siempre al fondo.
    tracks: list[dict] = []
    if timeline.captions:
        tracks.append(
            {
                "clips": [
                    {
                        "asset": {
                            "type": "title",
                            "text": cap.text,
                            "style": "subtitle",
                            "color": "#ffffff",
                            "size": "small",
                            "position": "bottom",
                        },
                        "start": cap.start_s,
                        "length": max(cap.end_s - cap.start_s, 0.1),
                    }
                    for cap in timeline.captions
                ]
            }
        )
    if title_clips:
        tracks.append({"clips": title_clips})
    tracks.append({"clips": media_clips})

    edit: dict = {
        "timeline": {"tracks": tracks},
        # Shotstack no admite resolution="custom": presets = preview|mobile|sd|hd|1080|4k.
        # Con size custom hay que omitir resolution y aspectRatio; para Reels usamos preset 1080 + 9:16.
        "output": {
            "resolution": "1080",
            "aspectRatio": "9:16",
            "fps": timeline.output.fps,
            "format": timeline.output.fmt,
        },
    }

    if timeline.voiceover is not None:
        edit["timeline"]["soundtrack"] = {
            "src": timeline.voiceover.audio_url,
            "effect": "fadeOut",
        }

    return edit
