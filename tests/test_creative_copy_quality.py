"""Pruebas del fallback creativo y del rechazo QA a meta-copy del brief."""

from agents.marketing_agents.copywriter import CopywriterAgent
from agents.marketing_agents.creative_fallback import (
    creative_copy_fallback,
    creative_strategy_fallback,
    looks_like_meta_brief_dump,
)
from agents.marketing_agents.quality import ContentQualityGuard
from agents.marketing_agents.schemas import BriefInput, StrategyOutput
from agents.marketing_agents.strategist import ContentStrategistAgent


def _amor_brief() -> BriefInput:
    return BriefInput(
        tema="Día del amor y amistad",
        publico_objetivo="parejas",
        red_social="instagram",
        objetivo="ventas",
        tono_marca="cercano",
        idioma="es",
    )


def test_old_stub_patterns_detected_as_meta() -> None:
    assert looks_like_meta_brief_dump(
        "Contenido ventas para parejas en instagram con enfoque cercano. Atraemos, informamos"
    )
    assert looks_like_meta_brief_dump(
        "¿Sabias que día del amor y amistad puede acelerar tus resultados?"
    )
    assert not looks_like_meta_brief_dump(
        "Este Día del Amor y la Amistad merece un momento juntos en la mesa."
    )


def test_creative_strategy_fallback_is_audience_facing() -> None:
    out = creative_strategy_fallback(_amor_brief())
    blob = f"{out.hook} {out.mensaje_base}".lower()
    assert "contenido ventas" not in blob
    assert "con enfoque" not in blob
    assert "acelerar tus resultados" not in blob
    assert "amor" in blob or "amistad" in blob or "pareja" in blob


def test_creative_copy_fallback_has_substance_and_tone() -> None:
    brief = _amor_brief()
    strategy = creative_strategy_fallback(brief)
    copy = creative_copy_fallback(brief, strategy)
    assert len(copy.copy_final) >= 80
    assert not looks_like_meta_brief_dump(copy.headline_for_image)
    assert not looks_like_meta_brief_dump(copy.subline_for_image)
    assert copy.cta
    assert copy.hashtags


def test_qa_rejects_meta_brief_dump() -> None:
    guard = ContentQualityGuard()
    q = guard.validate(
        "Contenido ventas para parejas en instagram con enfoque cercano.",
        "cercano",
        overlay_headline="¿Sabias que día del amor puede acelerar tus resultados?",
        overlay_subline="Contenido ventas para parejas",
    )
    assert q.approved is False
    assert any("brief" in r.lower() or "audiencia" in r.lower() for r in q.reasons)


def test_qa_approves_creative_caption() -> None:
    brief = _amor_brief()
    copy = creative_copy_fallback(brief, creative_strategy_fallback(brief))
    guard = ContentQualityGuard()
    q = guard.validate(
        copy.copy_final,
        brief.tono_marca,
        overlay_headline=copy.headline_for_image,
        overlay_subline=copy.subline_for_image,
    )
    assert q.approved is True


def test_strategist_without_llm_uses_creative_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.marketing_agents.strategist.get_llm",
        lambda: None,
    )
    out = ContentStrategistAgent().run(_amor_brief())
    assert "contenido ventas" not in out.mensaje_base.lower()
    assert "acelerar tus resultados" not in out.hook.lower()


def test_copywriter_without_llm_uses_creative_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.marketing_agents.copywriter.get_llm",
        lambda: None,
    )
    brief = _amor_brief()
    # Estrategia meta antigua (como la del stub previo) debe sanearse
    bad_strategy = StrategyOutput(
        tipo_post="educativo",
        hook="¿Sabias que día del amor y amistad puede acelerar tus resultados?",
        mensaje_base="Contenido ventas para parejas en instagram con enfoque cercano.",
        hashtags=["#x"],
    )
    out = CopywriterAgent().run(bad_strategy, brief=brief)
    blob = f"{out.copy_final} {out.headline_for_image} {out.subline_for_image}".lower()
    assert "contenido ventas" not in blob
    assert "acelerar tus resultados" not in blob
    assert len(out.copy_final) >= 80
