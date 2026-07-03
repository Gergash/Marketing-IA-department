"""Pruebas del contrato Timeline (video_timeline.py): validación Pydantic v2 y mapeo a Shotstack."""

import pytest
from pydantic import ValidationError

from agents.marketing_agents.video_timeline import (
    OutputSpec,
    Scene,
    Timeline,
    VoiceoverTrack,
    to_shotstack_edit,
)


def _scene(**overrides) -> Scene:
    defaults = dict(
        background_url="http://localhost:8000/static/images/bg1.png",
        headline="Titulo",
        subline="Sub",
        archetype="typographic_poster",
        duration_s=4.0,
        effect="zoomIn",
    )
    defaults.update(overrides)
    return Scene(**defaults)


def test_timeline_validates_with_scenes_and_voiceover() -> None:
    timeline = Timeline(
        scenes=[_scene(), _scene(duration_s=5.0), _scene(duration_s=3.0)],
        voiceover=VoiceoverTrack(audio_url="http://localhost:8000/static/audio/vo1.mp3", duration_s=12.0),
    )
    assert len(timeline.scenes) == 3
    assert timeline.output.width == 1080
    assert timeline.output.height == 1920
    assert timeline.output.fps == 30
    assert timeline.output.fmt == "mp4"


def test_scene_requires_background_url() -> None:
    with pytest.raises(ValidationError):
        Scene(headline="Titulo")


def test_output_spec_defaults_9_16() -> None:
    spec = OutputSpec()
    assert spec.width == 1080
    assert spec.height == 1920


def test_to_shotstack_edit_maps_scenes_to_clips_and_sums_durations() -> None:
    timeline = Timeline(
        scenes=[_scene(duration_s=4.0), _scene(duration_s=5.0), _scene(duration_s=3.0)],
        voiceover=VoiceoverTrack(audio_url="http://localhost:8000/static/audio/vo1.mp3", duration_s=12.0),
    )
    edit = to_shotstack_edit(timeline)

    assert edit["output"]["resolution"] or edit["output"]["size"]
    assert edit["output"]["aspectRatio"] == "9:16"
    assert edit["output"]["fps"] == 30
    assert edit["output"]["format"] == "mp4"

    tracks = edit["timeline"]["tracks"]
    # al menos un track de video (clips de escena) y un track/soundtrack de audio
    video_track = tracks[0]
    clips = video_track["clips"]
    assert len(clips) == 3

    total_length = sum(c["length"] for c in clips)
    assert total_length == pytest.approx(12.0)

    # start acumulativo
    assert clips[0]["start"] == pytest.approx(0.0)
    assert clips[1]["start"] == pytest.approx(4.0)
    assert clips[2]["start"] == pytest.approx(9.0)

    assert "soundtrack" in edit["timeline"] or any("audio" in t for t in tracks)


def test_to_shotstack_edit_without_voiceover_still_maps_clips() -> None:
    timeline = Timeline(scenes=[_scene(duration_s=4.0), _scene(duration_s=5.0)])
    edit = to_shotstack_edit(timeline)
    clips = edit["timeline"]["tracks"][0]["clips"]
    assert len(clips) == 2


def test_scene_negative_duration_rejected() -> None:
    with pytest.raises(ValidationError):
        Scene(background_url="http://x/y.png", headline="", subline="", duration_s=-1.0)


def test_timeline_rejects_scene_missing_narration() -> None:
    """Escena sin texto de narración (headline/subline vacíos) hace que el ensamblado del Timeline falle."""
    blank_scene = Scene(background_url="http://x/y.png", headline="", subline="")
    with pytest.raises(ValidationError):
        Timeline(scenes=[_scene(), blank_scene])


def test_duration_clamp_trims_when_voiceover_exceeds_30s() -> None:
    long_scenes = [_scene(duration_s=12.0) for _ in range(3)]  # 36s total
    timeline = Timeline(
        scenes=long_scenes,
        voiceover=VoiceoverTrack(audio_url="http://localhost:8000/static/audio/vo1.mp3", duration_s=36.0),
    )
    edit = to_shotstack_edit(timeline)
    clips = edit["timeline"]["tracks"][0]["clips"]
    total_length = sum(c["length"] for c in clips)
    assert total_length <= 30.0


def test_duration_clamp_holds_minimums_when_voiceover_under_15s() -> None:
    short_scenes = [_scene(duration_s=4.0), _scene(duration_s=4.0), _scene(duration_s=4.0)]  # 12s total
    timeline = Timeline(
        scenes=short_scenes,
        voiceover=VoiceoverTrack(audio_url="http://localhost:8000/static/audio/vo1.mp3", duration_s=10.0),
    )
    edit = to_shotstack_edit(timeline)
    clips = edit["timeline"]["tracks"][0]["clips"]
    total_length = sum(c["length"] for c in clips)
    # no se estira para llenar; mantiene duraciones mínimas de escena (no colapsa a 10s)
    assert total_length == pytest.approx(12.0)
