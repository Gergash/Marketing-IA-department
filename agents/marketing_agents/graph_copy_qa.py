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
    # Notas del usuario desde el checkpoint interactivo; pesan igual que el feedback de QA.
    user_notes: str
    # ThoughtStream / NullThoughtStream: narra cada ronda en vivo al dashboard.
    thoughts: object


def build_copy_qa_graph(
    copywriter: CopywriterAgent,
    guard: ContentQualityGuard,
):
    """Compila el grafo copy -> QA -> (revisar | fin). `max_attempts` va en el `invoke`."""

    def copywriter_node(state: CopyQAState) -> dict:
        """Nodo LangGraph: invoca al copywriter, opcionalmente con feedback del QA previo, y registra evento."""
        q_prev = state.get("quality")
        feedback = list(q_prev.reasons) if q_prev is not None and not q_prev.approved else []
        user_notes = (state.get("user_notes") or "").strip()
        if user_notes:
            feedback.insert(0, f"Petición explícita del usuario: {user_notes}")
        prev = state.get("attempt", 0)
        thoughts = state.get("thoughts")
        if thoughts is not None:
            thoughts.think(
                "copywriter",
                f"Escribiendo el copy (ronda {prev + 1})…"
                + (" aplicando el feedback recibido." if feedback else ""),
                round=prev + 1,
                feedback=feedback,
            )
        copy = copywriter.run(
            state["strategy"],
            qa_feedback=feedback or None,
            brand_context=getattr(state["brief"], "brand_context", "") or "",
        )
        if thoughts is not None:
            thoughts.output(
                "copywriter",
                f"Borrador listo: «{copy.headline_for_image or copy.copy_final[:80]}»",
                round=prev + 1,
                copy_final=copy.copy_final,
                headline=copy.headline_for_image,
                subline=copy.subline_for_image,
                cta=copy.cta,
                hashtags=list(copy.hashtags),
            )
        evt = {
            "node": "copywriter",
            "round": prev + 1,
            "qa_feedback_applied": bool(feedback),
            "feedback_reasons": list(feedback),
        }
        return {"copy": copy, "attempt": prev + 1, "events": [evt]}

    def qa_node(state: CopyQAState) -> dict:
        """Nodo LangGraph: valida el copy actual y añade evento de aprobación o motivos de rechazo."""
        thoughts = state.get("thoughts")
        if thoughts is not None:
            thoughts.think("qa", "Revisando tono, longitud y compliance del borrador…")
        q = guard.validate(
            state["copy"].copy_final,
            state["brief"].tono_marca,
            overlay_headline=state["copy"].headline_for_image,
        )
        if thoughts is not None:
            thoughts.output(
                "qa",
                "Copy aprobado." if q.approved else "Copy rechazado; lo devuelvo al copywriter.",
                approved=q.approved,
                reasons=list(q.reasons),
            )
        evt = {
            "node": "qa",
            "approved": q.approved,
            "reasons": list(q.reasons),
        }
        return {"quality": q, "events": [evt]}

    def route_after_qa(state: CopyQAState) -> str:
        """Arista condicional: terminar, o volver al copywriter si quedan intentos y el QA falló."""
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
    user_notes: str = "",
    thoughts=None,
) -> CopyQAState:
    """Ejecuta el grafo compilado con estado inicial (brief, strategy, contador de intentos y eventos vacíos)."""
    return compiled.invoke(
        {
            "brief": brief,
            "strategy": strategy,
            "max_attempts": max_attempts,
            "attempt": 0,
            "events": [],
            "user_notes": user_notes,
            "thoughts": thoughts,
        }
    )
