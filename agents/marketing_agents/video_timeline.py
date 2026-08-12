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
    # Narración hablada: si hay captions vacíos, se convierte en subtítulos automáticos.
    narration: str = ""
    archetype: str = "typographic_poster"  # reutiliza IDs de layout_archetypes para estilo de overlay
    duration_s: float = Field(default=4.0, gt=0)
    effect: str = "zoomIn"  # token provider-neutral (Ken Burns); mapeado a Shotstack en to_shotstack_edit
    asset_type: Literal["image", "video"] = "image"
    # trim_in/trim_out solo tienen sentido para asset_type="video" (clip fuente recortado)
    trim_in: float = 0.0
    trim_out: float | None = None


class Caption(BaseModel):
    """Cue de subtítulo sincronizado a timestamps de palabra (Whisper) o a la narración de escena."""

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
_MAX_TITLE_CHARS = 28
_MAX_TITLE_LINE = 16
_MAX_SUBTITLE_CHARS = 42


def _wrap_short(text: str, *, max_chars: int, line_width: int) -> str:
    """Recorta y parte en 1–2 líneas cortas para que Shotstack no desborde el frame 9:16."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return ""
    if len(cleaned) > max_chars:
        cut = cleaned[: max_chars - 1]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        cleaned = f"{cut}…"
    words = cleaned.split()
    if not words:
        return ""
    line1: list[str] = []
    line2: list[str] = []
    for word in words:
        trial = " ".join(line1 + [word])
        if not line2 and len(trial) <= line_width:
            line1.append(word)
        else:
            line2.append(word)
    if not line2:
        return " ".join(line1)
    second = " ".join(line2)
    if len(second) > line_width:
        second = second[: line_width - 1].rsplit(" ", 1)[0] + "…"
    return f"{' '.join(line1)}\n{second}"


def fit_title_overlay(headline: str, subline: str = "") -> str:
    """Headline corto para overlay superior; el subline largo va a subtítulos, no al título grande."""
    primary = (headline or "").strip() or (subline or "").strip()
    return _wrap_short(primary, max_chars=_MAX_TITLE_CHARS, line_width=_MAX_TITLE_LINE)


def _chunk_subtitle(text: str, max_chars: int = _MAX_SUBTITLE_CHARS) -> list[str]:
    """Parte una narración en cues de subtítulo legibles (por palabras)."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return []
    words = cleaned.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def build_captions_from_narrations(
    narrations: list[str],
    durations: list[float],
    *,
    max_chars_per_cue: int = _MAX_SUBTITLE_CHARS,
) -> list[Caption]:
    """Genera subtítulos a partir de la narración de cada escena, repartidos en su duración."""
    captions: list[Caption] = []
    cursor = 0.0
    for narration, length in zip(narrations, durations):
        chunks = _chunk_subtitle(narration, max_chars_per_cue)
        if not chunks or length <= 0:
            cursor += max(length, 0.0)
            continue
        slice_len = length / len(chunks)
        for i, chunk in enumerate(chunks):
            start = cursor + i * slice_len
            end = cursor + (i + 1) * slice_len
            captions.append(Caption(text=chunk, start_s=start, end_s=max(end, start + 0.1)))
        cursor += length
    return captions


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

        # Título corto arriba (size small). El texto largo va en subtítulos, no como "large" centrado.
        title_text = fit_title_overlay(scene.headline, scene.subline)
        if title_text:
            title_clips.append(
                {
                    "asset": {
                        "type": "title",
                        "text": title_text,
                        "style": _SHOTSTACK_TITLE_STYLE,
                        "color": "#ffffff",
                        "size": "small",
                        "position": "top",
                    },
                    "start": start,
                    "length": length,
                }
            )
        start += length

    captions = list(timeline.captions)
    if not captions:
        narrations = [(s.narration or "").strip() for s in timeline.scenes]
        if any(narrations):
            captions = build_captions_from_narrations(narrations, durations)
        else:
            # Fallback: subtítulos desde headline/subline si no hay narración explícita
            fallback = [
                " ".join(p for p in (s.headline, s.subline) if p).strip() for s in timeline.scenes
            ]
            if any(fallback):
                captions = build_captions_from_narrations(fallback, durations)

    # tracks[0] = capa superior. Media siempre al fondo.
    tracks: list[dict] = []
    if captions:
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
                            "position": "center",
                        },
                        "start": cap.start_s,
                        "length": max(cap.end_s - cap.start_s, 0.1),
                    }
                    for cap in captions
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
