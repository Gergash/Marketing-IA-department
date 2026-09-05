"""Tests: revisión humana en prompts visuales (personas / no truncar notas)."""

from agents.marketing_agents.revision_prompt import (
    compose_visual_prompt,
    people_priority_block,
    revision_requests_people,
    revision_requests_scene_change,
)
from agents.marketing_agents.visual_prompt_guards import with_photo_only_guard


def test_detects_people_and_scene_revision() -> None:
    notes = "agrega 2 personas sentadas en las sillas para parejas"
    assert revision_requests_people(notes)
    assert revision_requests_scene_change(notes)
    assert not revision_requests_people("cambia el color del botón CTA")


def test_compose_keeps_revision_when_base_is_huge() -> None:
    base = "atmosphere photo " * 800  # >> 4000 chars
    notes = "agrega 2 personas sentadas en las sillas"
    out = compose_visual_prompt(base, model="gpt-image-2", revision_notes=notes)
    assert "CRITICAL" in out
    assert "personas sentadas" in out.lower() or "couple" in out.lower()
    assert len(out) <= 4000
    # La revisión debe estar al INICIO (no truncada)
    assert out.lower().startswith("critical")


def test_people_guard_suffix() -> None:
    p = with_photo_only_guard("romantic dinner table", allow_people=True)
    assert "INCLUDES the requested people" in p
    assert "Empty chairs" in p or "empty chairs" in p.lower()


def test_people_priority_block_mentions_empty_chairs_wrong() -> None:
    block = people_priority_block("pon una pareja sentada")
    assert "Empty furniture" in block or "empty" in block.lower()
    assert "pareja sentada" in block


def test_scene_edit_prompt_forbids_typography() -> None:
    from agents.marketing_agents.revision_prompt import build_scene_edit_prompt

    out = build_scene_edit_prompt("agrega 2 personas sentadas en las sillas")
    low = out.lower()
    assert "personas sentadas" in low or "people" in low
    assert "do not add" in low or "not add" in low
    assert "typography" in low or "letters" in low
    # No debe arrastrar copy de marketing típico
    assert "día del amor" not in low
    assert "headline" not in low


def test_scene_edit_prompt_default_adds_people() -> None:
    from agents.marketing_agents.revision_prompt import build_scene_edit_prompt

    out = build_scene_edit_prompt(None)
    assert "people" in out.lower() or "seated" in out.lower()
    assert "text" in out.lower() or "typography" in out.lower()


def test_scene_edit_prompt_uses_revision_notes() -> None:
    from agents.marketing_agents.revision_prompt import build_scene_edit_prompt

    out = build_scene_edit_prompt(None, revision_notes="pon una pareja sentada en las sillas")
    assert out.lower().startswith("critical")
    assert "pareja sentada" in out.lower()
