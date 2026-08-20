"""Regresión: los dos parches de coerción de `content_format` aceptan "reel" sin romper feed/story."""

from agents.marketing_agents.image_specs import (
    NETWORKS,
    formats_for_network,
    resolve_image_spec,
)
from gateway.app.services.pipeline_service import _normalize_content_format


def test_normalize_content_format_accepts_reel() -> None:
    assert _normalize_content_format("reel") == "reel"


def test_normalize_content_format_accepts_user_clip_reel() -> None:
    assert _normalize_content_format("user_clip_reel") == "user_clip_reel"


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


def test_resolve_image_spec_user_clip_reel_is_vertical_9_16_not_feed() -> None:
    spec = resolve_image_spec("instagram", "user_clip_reel")
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


def test_normalize_content_format_accepts_universal() -> None:
    assert _normalize_content_format("universal") == "universal"


def test_universal_spec_is_identical_across_networks() -> None:
    specs = {resolve_image_spec(net_id, "universal") for net_id, _label in NETWORKS}
    assert len(specs) == 1
    universal = specs.pop()
    assert universal.width == 1080 and universal.height == 1080


def test_feed_spec_differs_per_network() -> None:
    assert resolve_image_spec("linkedin", "feed") == resolve_image_spec("linkedin", "feed")
    assert resolve_image_spec("linkedin", "feed").width == 1200
    assert resolve_image_spec("linkedin", "feed").height == 627
    assert resolve_image_spec("x", "feed").height == 675
    assert resolve_image_spec("tiktok", "feed").height == 1920


def test_every_network_offers_the_universal_format() -> None:
    for net_id, _label in NETWORKS:
        ids = [f["id"] for f in formats_for_network(net_id)]
        assert "universal" in ids, net_id


def test_linkedin_does_not_offer_story_or_reel() -> None:
    ids = [f["id"] for f in formats_for_network("linkedin")]
    assert ids == ["feed", "universal"]


def test_tiktok_has_no_horizontal_feed_post() -> None:
    ids = [f["id"] for f in formats_for_network("tiktok")]
    assert "feed" not in ids
    assert "reel" in ids


def test_formats_for_network_reports_dimensions_and_video_flag() -> None:
    by_id = {f["id"]: f for f in formats_for_network("instagram")}
    assert (by_id["feed"]["width"], by_id["feed"]["height"]) == (1080, 1350)
    assert by_id["reel"]["is_video"] is True
    assert by_id["universal"]["is_video"] is False


def test_unknown_network_falls_back_to_all_formats() -> None:
    ids = [f["id"] for f in formats_for_network("mastodon")]
    assert ids == ["feed", "story", "reel", "user_clip_reel", "universal"]
