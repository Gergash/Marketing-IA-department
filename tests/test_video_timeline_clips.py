"""Pruebas de extensión video-asset en video_timeline.py: asset_type, trim, captions.

Regresión crítica: el camino solo-imagen (comportamiento pre-cambio) debe permanecer
estructuralmente idéntico; estos tests fijan esa forma exacta.
"""

import pytest
from pydantic import ValidationError

from agents.marketing_agents.video_timeline import (
    Caption,
    Scene,
    Timeline,
    to_shotstack_edit,
)


def _image_scene(**overrides) -> Scene:
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


def test_existing_image_reel_output_structurally_unchanged() -> None:
    """Imagen + overlay: subtítulos (auto) + títulos cortos arriba + media abajo."""
    timeline = Timeline(
        scenes=[_image_scene(duration_s=4.0, narration="Hola mundo de prueba para subtítulos")]
    )
    edit = to_shotstack_edit(timeline)
    tracks = edit["timeline"]["tracks"]
    assert len(tracks) == 3  # captions + títulos + media

    caption_clip = tracks[0]["clips"][0]
    assert caption_clip["asset"]["type"] == "title"
    assert caption_clip["asset"]["style"] == "subtitle"
    assert caption_clip["asset"]["position"] == "bottom"

    title_clip = tracks[1]["clips"][0]
    assert title_clip["asset"]["type"] == "title"
    assert title_clip["asset"]["size"] == "small"
    assert title_clip["asset"]["position"] == "top"
    assert "Titulo" in title_clip["asset"]["text"]
    assert title_clip["start"] == pytest.approx(0.0)
    assert title_clip["length"] == pytest.approx(4.0)

    media_clip = tracks[2]["clips"][0]
    assert media_clip["asset"] == {"type": "image", "src": "http://localhost:8000/static/images/bg1.png"}
    assert media_clip["start"] == pytest.approx(0.0)
    assert media_clip["length"] == pytest.approx(4.0)
    assert media_clip["effect"] == "zoomIn"
    assert "title_asset" not in media_clip


def test_fit_title_overlay_truncates_long_headlines() -> None:
    from agents.marketing_agents.video_timeline import fit_title_overlay

    long = "MEJORES PRÁCTICAS PARA EMPRENDEDORES DIGITALES"
    fitted = fit_title_overlay(long)
    assert len(fitted.replace("\n", "")) <= 30
    assert "…" in fitted or len(long) <= 28


def test_auto_captions_from_narration_always_present() -> None:
    timeline = Timeline(
        scenes=[
            _image_scene(
                duration_s=4.0,
                headline="Hook",
                narration="Los emprendedores saben que los datos son clave para crecer.",
            )
        ]
    )
    edit = to_shotstack_edit(timeline)
    caption_track = edit["timeline"]["tracks"][0]
    assert caption_track["clips"]
    assert all(c["asset"]["style"] == "subtitle" for c in caption_track["clips"])
    assert all(c["asset"]["position"] == "bottom" for c in caption_track["clips"])
    joined = " ".join(c["asset"]["text"] for c in caption_track["clips"])
    assert "emprendedores" in joined.lower() or "datos" in joined.lower()


def test_scene_defaults_asset_type_image() -> None:
    scene = _image_scene()
    assert scene.asset_type == "image"
    assert scene.trim_in == 0.0
    assert scene.trim_out is None


def test_video_scene_emits_trim_matching_in_out() -> None:
    scene = Scene(
        background_url="http://localhost:8000/static/clips/clip1.mp4",
        asset_type="video",
        trim_in=2.0,
        trim_out=8.5,
        duration_s=6.5,
    )
    timeline = Timeline(scenes=[scene])
    edit = to_shotstack_edit(timeline)
    # Sin headline/subline → solo track de media
    clip = edit["timeline"]["tracks"][0]["clips"][0]

    assert clip["asset"]["type"] == "video"
    assert clip["asset"]["src"] == "http://localhost:8000/static/clips/clip1.mp4"
    assert clip["asset"]["trim"] == pytest.approx(2.0)
    assert clip["length"] == pytest.approx(6.5)


def test_video_scene_without_narration_is_valid() -> None:
    """Escenas de video no requieren headline/subline (a diferencia de las de imagen)."""
    scene = Scene(
        background_url="http://localhost:8000/static/clips/clip1.mp4",
        asset_type="video",
        headline="",
        subline="",
    )
    timeline = Timeline(scenes=[scene])
    assert timeline.scenes[0].asset_type == "video"


def test_image_scene_still_requires_narration() -> None:
    blank = Scene(background_url="http://x/y.png", headline="", subline="")
    with pytest.raises(ValidationError):
        Timeline(scenes=[blank])


def test_captions_track_aligns_to_word_timestamps() -> None:
    scene = _image_scene()
    captions = [
        Caption(text="hola", start_s=0.0, end_s=0.4),
        Caption(text="mundo", start_s=0.4, end_s=0.9),
    ]
    timeline = Timeline(scenes=[scene], captions=captions)
    edit = to_shotstack_edit(timeline)

    tracks = edit["timeline"]["tracks"]
    # captions (arriba) → títulos → media
    assert len(tracks) == 3
    caption_clips = tracks[0]["clips"]
    assert caption_clips[0]["start"] == pytest.approx(0.0)
    assert caption_clips[0]["length"] == pytest.approx(0.4)
    assert caption_clips[1]["start"] == pytest.approx(0.4)
    assert caption_clips[1]["length"] == pytest.approx(0.5)
    assert tracks[1]["clips"][0]["asset"]["type"] == "title"
    assert tracks[2]["clips"][0]["asset"]["type"] == "image"


def test_empty_captions_still_auto_subtitles_from_headline() -> None:
    """Si captions=[] pero hay headline, siempre se generan subtítulos (política Reels)."""
    timeline = Timeline(scenes=[_image_scene()], captions=[])
    edit = to_shotstack_edit(timeline)
    # captions (auto) + títulos + media
    assert len(edit["timeline"]["tracks"]) == 3
    assert edit["timeline"]["tracks"][0]["clips"][0]["asset"]["style"] == "subtitle"


def test_video_scene_without_text_has_only_media_track() -> None:
    """Clip de usuario sin narración ni headline: solo media (sin fallar)."""
    scene = Scene(
        background_url="http://localhost:8000/static/clips/silent.mp4",
        asset_type="video",
        headline="",
        subline="",
        narration="",
        duration_s=3.0,
    )
    edit = to_shotstack_edit(Timeline(scenes=[scene], captions=[]))
    assert len(edit["timeline"]["tracks"]) == 1
    assert edit["timeline"]["tracks"][0]["clips"][0]["asset"]["type"] == "video"