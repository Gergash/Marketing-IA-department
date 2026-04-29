from unittest.mock import MagicMock

import pytest

from agents.marketing_agents.copywriter import CopywriterAgent
from agents.marketing_agents.graph_copy_qa import build_copy_qa_graph
from agents.marketing_agents.quality import ContentQualityGuard, QualityReview
from agents.marketing_agents.schemas import BriefInput, CopyOutput, StrategyOutput


def test_copy_qa_graph_retries_then_approves(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = ContentQualityGuard()
    calls: dict[str, int] = {"n": 0}

    def fake_validate(text: str, brand_tone: str) -> QualityReview:
        calls["n"] += 1
        if calls["n"] == 1:
            return QualityReview(approved=False, reasons=["must revise"])
        return QualityReview(approved=True, reasons=[])

    monkeypatch.setattr(guard, "validate", fake_validate)

    cw = MagicMock(spec=CopywriterAgent)
    first = CopyOutput(copy_final="v1", hashtags=["#a"], cta="c1")
    second = CopyOutput(copy_final="v2", hashtags=["#a"], cta="c2")
    cw.run.side_effect = [first, second]

    graph = build_copy_qa_graph(cw, guard)
    brief = BriefInput(
        tema="marketing",
        publico_objetivo="pymes",
        red_social="instagram",
        objetivo="branding",
    )
    strategy = StrategyOutput(
        tipo_post="educativo",
        hook="h",
        mensaje_base="m",
        hashtags=["#t"],
    )
    out = graph.invoke(
        {"brief": brief, "strategy": strategy, "max_attempts": 3, "attempt": 0, "events": []}
    )

    assert out["quality"].approved is True
    assert out["copy"].copy_final == "v2"
    assert cw.run.call_count == 2
    assert cw.run.call_args_list[1].kwargs.get("qa_feedback") == ["must revise"]
    assert len(out["events"]) == 4


def test_copy_qa_graph_exhausts_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = ContentQualityGuard()
    monkeypatch.setattr(
        guard,
        "validate",
        lambda text, tone: QualityReview(approved=False, reasons=["always bad"]),
    )

    cw = MagicMock(spec=CopywriterAgent)
    cw.run.return_value = CopyOutput(copy_final="x", hashtags=[], cta="c")

    graph = build_copy_qa_graph(cw, guard)
    brief = BriefInput(
        tema="marketing",
        publico_objetivo="pymes",
        red_social="instagram",
        objetivo="branding",
    )
    strategy = StrategyOutput(
        tipo_post="educativo",
        hook="h",
        mensaje_base="m",
        hashtags=["#t"],
    )
    out = graph.invoke(
        {"brief": brief, "strategy": strategy, "max_attempts": 2, "attempt": 0, "events": []}
    )

    assert out["quality"].approved is False
    assert cw.run.call_count == 2
