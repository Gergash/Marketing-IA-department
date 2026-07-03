"""Contrato JSON provider-neutral para video (Reels): Timeline Pydantic v2 + mapeo a Shotstack.

Este módulo no hace I/O; es el único lugar donde se filtra la forma del JSON de Shotstack.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Banda objetivo de duración total del reel (spec: 15-30s)
_MIN_TOTAL_DURATION_S = 15.0
_MAX_TOTAL_DURATION_S = 30.0


class Scene(BaseModel):
    """Una escena del reel: fondo fijo (fal.ai) + overlay de texto + efecto Ken Burns."""

    background_url: str = Field(min_length=1)
    headline: str = ""
    subline: str = ""
    archetype: str = "typographic_poster"  # reutiliza IDs de layout_archetypes para estilo de overlay
    duration_s: float = Field(default=4.0, gt=0)
    effect: str = "zoomIn"  # token provider-neutral (Ken Burns); mapeado a Shotstack en to_shotstack_edit


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
    output: OutputSpec = Field(default_factory=OutputSpec)

    @field_validator("scenes")
    @classmethod
    def _scenes_have_narration(cls, scenes: list[Scene]) -> list[Scene]:
        """Cada escena debe tener texto de narración (headline o subline); si no, error de validación."""
        for scene in scenes:
            if not (scene.headline or scene.subline):
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
        scale = _MAX_TOTAL_DURATION_S / base_total
        return [d * scale for d in base]

    if voice_duration < _MIN_TOTAL_DURATION_S:
        return base

    scale = voice_duration / base_total
    return [d * scale for d in base]


def to_shotstack_edit(timeline: Timeline) -> dict:
    """Mapea el Timeline provider-neutral a la forma de JSON `edit` que espera la API de Shotstack."""
    durations = _clamped_scene_durations(timeline)

    clips: list[dict] = []
    start = 0.0
    for scene, length in zip(timeline.scenes, durations):
        clip: dict = {
            "asset": {"type": "image", "src": scene.background_url},
            "start": start,
            "length": length,
            "effect": scene.effect,
        }
        if scene.headline or scene.subline:
            clip["title_asset"] = {
                "type": "title",
                "text": scene.headline,
                "sub_text": scene.subline,
                "style": scene.archetype,
            }
        clips.append(clip)
        start += length

    tracks: list[dict] = [{"clips": clips}]

    edit: dict = {
        "timeline": {"tracks": tracks},
        "output": {
            "resolution": "custom",
            "size": {"width": timeline.output.width, "height": timeline.output.height},
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
