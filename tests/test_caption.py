"""Tests del ensamblado de caption: hashtags + link en la descripción."""

from agents.marketing_agents.caption import (
    build_publish_caption,
    ensure_hashtags,
    normalize_hashtags,
)


def test_normalize_hashtags_adds_hash_and_dedupes() -> None:
    assert normalize_hashtags(["IA", "#IA", "#Marketing", ""]) == ["#IA", "#Marketing"]


def test_ensure_hashtags_fallback_when_empty() -> None:
    tags = ensure_hashtags([], fallback=["#Foo"])
    assert tags == ["#Foo"]
    assert ensure_hashtags([])  # defaults no vacíos


def test_build_publish_caption_appends_hashtags_and_link() -> None:
    caption = build_publish_caption(
        "Hook del post. Comenta y conectemos.",
        ["#IA", "MarketingDigital"],
        link_url="https://powerupsagencia.com",
    )
    assert "Hook del post" in caption
    assert "https://powerupsagencia.com" in caption
    assert "#IA" in caption
    assert "#MarketingDigital" in caption
    # Link y hashtags después del cuerpo
    assert caption.index("Hook") < caption.index("https://")
    assert caption.index("https://") < caption.index("#IA")


def test_build_publish_caption_does_not_duplicate_existing_tags() -> None:
    caption = build_publish_caption(
        "Texto con #IA ya incluido",
        ["#IA", "#Extra"],
    )
    assert caption.count("#IA") == 1
    assert "#Extra" in caption


def test_build_publish_caption_always_has_hashtags() -> None:
    caption = build_publish_caption("Solo texto", [])
    assert "#" in caption
