"""Regresión: los dos parches de coerción de `content_format` aceptan "reel" sin romper feed/story."""

from agents.marketing_agents.image_specs import resolve_image_spec
from gateway.app.services.pipeline_service import _normalize_content_format


def test_normalize_content_format_accepts_reel() -> None:
    assert _normalize_content_format("reel") == "reel"


def test_normalize_content_format_still_accepts_feed_and_story() -> None:
    assert _normalize_content_format("feed") == "feed"
    assert _normalize_content_format("story") == "story"


def test_normalize_content_format_unknown_value_coerces_to_feed() -> None:
    assert _normalize_content_format("bogus") == "feed"
    assert _normalize_content_format(None) == "feed"


def test_resolve_image_spec_reel_is_vertical_9_16() -> None:
    spec = resolve_image_spec("instagram", "reel")
    assert spec.width == 1080
    assert spec.height == 1920


def test_resolve_image_spec_unknown_format_still_coerces_to_feed() -> None:
    spec = resolve_image_spec("instagram", "bogus")
    feed_spec = resolve_image_spec("instagram", "feed")
    assert spec == feed_spec


def test_resolve_image_spec_feed_and_story_unchanged() -> None:
    feed = resolve_image_spec("instagram", "feed")
    story = resolve_image_spec("instagram", "story")
    assert feed.width == 1080 and feed.height == 1350
    assert story.width == 1080 and story.height == 1920
