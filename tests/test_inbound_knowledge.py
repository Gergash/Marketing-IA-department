"""Doctrina inbound: módulo de conocimiento inyectado en prompts de agentes."""

from agents.marketing_agents.copywriter import _SYSTEM as COPY_SYSTEM
from agents.marketing_agents.knowledge import CONTENT_GOALS, INBOUND_DOCTRINE, inbound_system_addendum
from agents.marketing_agents.knowledge.inbound_marketing import CONTENT_GOALS as GOALS_DIRECT
from agents.marketing_agents.strategist import _SYSTEM as STRAT_SYSTEM
from agents.marketing_agents.video_script import _SYSTEM as VIDEO_SYSTEM


def test_content_goals_order() -> None:
    assert CONTENT_GOALS == ("entretener", "informacion", "conexion")
    assert GOALS_DIRECT == CONTENT_GOALS


def test_doctrine_mentions_journey_and_sources() -> None:
    text = INBOUND_DOCTRINE.lower()
    assert "atraer" in text
    assert "convertir" in text
    assert "cerrar" in text
    assert "deleitar" in text
    assert "entretener" in text
    assert "conexion" in text or "conexión" in text
    assert "hubspot" in text or "cyberclick" in text


def test_addendum_role_focus() -> None:
    strat = inbound_system_addendum(role="strategist")
    copy = inbound_system_addendum(role="copywriter")
    video = inbound_system_addendum(role="video_script")
    assert "estratega" in strat.lower()
    assert "copywriter" in copy.lower()
    assert "guionista" in video.lower() or "reels" in video.lower()


def test_agent_systems_include_inbound_doctrine() -> None:
    for system in (STRAT_SYSTEM, COPY_SYSTEM, VIDEO_SYSTEM):
        assert "Inbound marketing" in system or "inbound" in system.lower()
        assert "Entretener" in system or "ENTRETENER" in system
        assert "Attract" in system or "ATRAER" in system or "Atraer" in system
