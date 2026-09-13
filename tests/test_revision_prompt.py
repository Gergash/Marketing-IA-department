"""Tests: revisión humana en prompts visuales (personas / tipografía / no truncar notas)."""

from agents.marketing_agents.revision_prompt import (
    compose_visual_prompt,
    parse_typography_revision,
    people_priority_block,
    revision_requests_people,
    revision_requests_scene_change,
    revision_requests_typography,
    scene_revision_notes,
)
from agents.marketing_agents.visual_prompt_guards import with_photo_only_guard


def test_detects_people_and_scene_revision() -> None:
    notes = "agrega 2 personas sentadas en las sillas para parejas"
    assert revision_requests_people(notes)
    assert revision_requests_scene_change(notes)
    assert not revision_requests_people("cambia el color del botón CTA")


def test_typography_notes_are_not_scene_change() -> None:
    notes = "cambia la tipografía a sans-serif Montserrat y texto más grande en blanco"
    assert revision_requests_typography(notes)
    assert not revision_requests_scene_change(notes)
    assert scene_revision_notes(notes) is None
    typo = parse_typography_revision(notes)
    assert typo.requested
    assert typo.style == "sans"
    assert typo.family_id == "montserrat"
    assert typo.text_color_hex == "#FFFFFF"
    assert typo.size_scale > 1.0


def test_parse_font_and_color_requests() -> None:
    azul = parse_typography_revision("cambia el color del texto a azul")
    assert azul.requested
    assert azul.text_color_hex == "#1D4ED8"
    assert not revision_requests_scene_change("cambia el color del texto a azul")

    hex_c = parse_typography_revision("texto en #EA580C")
    assert hex_c.text_color_hex == "#EA580C"

    accent = parse_typography_revision("color de acento dorado")
    assert accent.requested
    assert accent.accent_hex == "#C9A227" or accent.text_color_hex == "#C9A227"

    rotate = parse_typography_revision("cambia la fuente")
    assert rotate.requested
    assert rotate.rotate_family is True
    assert rotate.family_id is None


def test_compose_skips_typography_only_notes() -> None:
    base = "atmosphere photo of a restaurant"
    notes = "cambia la tipografía a cursiva"
    out = compose_visual_prompt(base, model="gpt-image-2", revision_notes=notes)
    assert "CRITICAL" not in out
    assert "tipografía" not in out.lower()
    assert "atmosphere photo" in out


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


def test_scene_edit_ignores_typography_only_revision() -> None:
    from agents.marketing_agents.revision_prompt import build_scene_edit_prompt

    out = build_scene_edit_prompt(
        None, revision_notes="cambia la tipografía a Montserrat blanco"
    )
    # No debe meter la petición tipográfica como CRITICAL SCENE EDIT
    assert "montserrat" not in out.lower()
    assert "tipografía" not in out.lower()


def test_designer_applies_typography_revision(monkeypatch) -> None:
    """Revisión tipográfica debe llegar al overlay Pillow, no al edit de escena."""
    from agents.marketing_agents.designer import DesignerAgent
    from agents.marketing_agents.schemas import BriefInput, CopyOutput, StrategyOutput

    captured: dict = {}

    def _fake_compose(url, **kwargs):
        captured.update(kwargs)
        return "http://localhost:8000/static/images/x.png", 1080, 1350, "user_overlay"

    monkeypatch.setattr(
        "agents.marketing_agents.designer.compose_from_user_asset", _fake_compose
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.resolve_brand_cues",
        lambda *a, **k: type(
            "C",
            (),
            {
                "has_signal": False,
                "suggested_archetype": None,
                "font_names": [],
                "logo_paths": [],
                "palette_hex": [],
            },
        )(),
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.apply_brand_to_archetype", lambda a, c: a
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.resolve_brand_font_paths", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.brand_priority_prompt_block", lambda *a, **k: ""
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.extract_brand_name_candidates", lambda *a, **k: []
    )

    class _S:
        image_provider = "mock"
        venice_image_model = "gpt-image-2"

    monkeypatch.setattr("gateway.app.core.settings.get_settings", lambda: _S())

    out = DesignerAgent().run(
        BriefInput(
            tema="cena",
            publico_objetivo="parejas",
            red_social="instagram",
            objetivo="branding",
        ),
        CopyOutput(
            copy_final="Ven a cenar",
            headline_for_image="Cena íntima",
            subline_for_image="Reserva ya",
            hashtags=["#cena"],
            cta="Reserva",
        ),
        StrategyOutput(
            tipo_post="feed",
            hook="Cena íntima",
            mensaje_base="Ven",
            hashtags=["#cena"],
        ),
        user_asset_url="/static/uploads/site.jpg",
        alter_image_with_ai=True,
        revision_notes="cambia la tipografía a Montserrat, texto blanco más grande",
    )
    assert out.design_source == "user_overlay"
    assert captured.get("alter_with_ai") is False  # tipografía sola: no re-editar foto
    assert captured.get("typography_family_id") == "montserrat"
    assert captured.get("typography_style") in ("sans", None) or captured.get(
        "typography_family_id"
    )
    assert captured.get("force_text_hex") == "#FFFFFF"
    assert float(captured.get("title_size_scale") or 1) > 1.0
    assert captured.get("revision_notes") in (None, "")


def test_designer_escape_script_on_generic_font_change(monkeypatch) -> None:
    """«Cambia la tipografía» sin nombre debe salir de Great Vibes (script de campaña)."""
    from agents.marketing_agents.designer import DesignerAgent
    from agents.marketing_agents.schemas import BriefInput, CopyOutput, StrategyOutput

    captured: dict = {}

    def _fake_compose(url, **kwargs):
        captured.update(kwargs)
        return "http://localhost:8000/static/images/x.png", 1080, 1350, "user_overlay"

    monkeypatch.setattr(
        "agents.marketing_agents.designer.compose_from_user_asset", _fake_compose
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.resolve_brand_cues",
        lambda *a, **k: type(
            "C",
            (),
            {
                "has_signal": True,
                "suggested_archetype": "brand_campaign_piece",
                "font_names": [],
                "logo_paths": [],
                "palette_hex": ["#C9A227"],
            },
        )(),
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.apply_brand_to_archetype", lambda a, c: a
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.resolve_brand_font_paths", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.brand_priority_prompt_block", lambda *a, **k: ""
    )
    monkeypatch.setattr(
        "agents.marketing_agents.designer.extract_brand_name_candidates", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "gateway.app.core.settings.get_settings",
        lambda: type("S", (), {"image_provider": "mock", "venice_image_model": "gpt-image-2"})(),
    )

    DesignerAgent().run(
        BriefInput(
            tema="Chimichurri significa amistad",
            publico_objetivo="clientes",
            red_social="instagram",
            objetivo="branding",
            brand_context="manual de marca",
        ),
        CopyOutput(
            copy_final="Chimichurri",
            headline_for_image="Chimichurri significa amistad",
            subline_for_image="",
            hashtags=["#x"],
            cta="",
        ),
        StrategyOutput(
            tipo_post="feed",
            hook="Chimichurri",
            mensaje_base="amistad",
            hashtags=["#x"],
        ),
        user_asset_url="/static/uploads/site.jpg",
        revision_notes="cambia esta tipografía, usa una fuente sans-serif moderna",
    )
    assert captured.get("typography_family_id") not in (None, "", "script_campaign")
    assert captured.get("typography_style") in ("sans", None) or captured.get(
        "typography_family_id"
    )
    # No debe pedir script
    assert captured.get("typography_style") != "script"
