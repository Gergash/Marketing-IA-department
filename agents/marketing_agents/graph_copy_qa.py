"""
Subgrafo LangGraph: bucle Copywriter <-> QA/Compliance.

Solo esta zona usa LangGraph: trazabilidad por `events`, reintentos y ramificación.
El resto del pipeline (estratega -> [este grafo] -> diseño -> publicador) sigue siendo Python lineal.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from .copywriter import CopywriterAgent
from .quality import ContentQualityGuard, QualityReview
from .schemas import BriefInput, CopyOutput, StrategyOutput


class CopyQAState(TypedDict, total=False):
    """Estado compartido entre nodos del bucle copy/QA."""

    brief: BriefInput
    strategy: StrategyOutput
    copy: CopyOutput
    quality: QualityReview
    attempt: int
    max_attempts: int
    events: Annotated[list[dict], operator.add]


def build_copy_qa_graph(
    copywriter: CopywriterAgent,
    guard: ContentQualityGuard,
):
    """Compila el grafo copy -> QA -> (revisar | fin). `max_attempts` va en el `invoke`."""

    def copywriter_node(state: CopyQAState) -> dict:
        q_prev = state.get("quality")
        feedback = q_prev.reasons if q_prev is not None and not q_prev.approved else None
        prev = state.get("attempt", 0)
        copy = copywriter.run(state["strategy"], qa_feedback=feedback)
        evt = {
            "node": "copywriter",
            "round": prev + 1,
            "qa_feedback_applied": feedback is not None,
            "feedback_reasons": list(feedback) if feedback else [],
        }
        return {"copy": copy, "attempt": prev + 1, "events": [evt]}

    def qa_node(state: CopyQAState) -> dict:
        q = guard.validate(state["copy"].copy_final, state["brief"].tono_marca)
        evt = {
            "node": "qa",
            "approved": q.approved,
            "reasons": list(q.reasons),
        }
        return {"quality": q, "events": [evt]}

    def route_after_qa(state: CopyQAState) -> str:
        if state["quality"].approved:
            return "finish"
        if state["attempt"] < state["max_attempts"]:
            return "revise"
        return "finish"

    graph = StateGraph(CopyQAState)
    graph.add_node("copywriter", copywriter_node)
    graph.add_node("qa", qa_node)
    graph.set_entry_point("copywriter")
    graph.add_edge("copywriter", "qa")
    graph.add_conditional_edges(
        "qa",
        route_after_qa,
        {"revise": "copywriter", "finish": END},
    )
    return graph.compile()


def invoke_copy_qa(
    compiled,
    *,
    brief: BriefInput,
    strategy: StrategyOutput,
    max_attempts: int,
) -> CopyQAState:
    return compiled.invoke(
        {
            "brief": brief,
            "strategy": strategy,
            "max_attempts": max_attempts,
            "attempt": 0,
            "events": [],
        }
    )
