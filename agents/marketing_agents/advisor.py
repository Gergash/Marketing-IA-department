"""Asesor creativo conversacional: diseñador + productor + mercadólogo + coach de marca."""

from __future__ import annotations

import structlog

from .brand_manual import load_brand_text
from .knowledge import inbound_system_addendum
from .llm import get_llm

logger = structlog.get_logger(__name__)

_SYSTEM = """\
Eres el Asesor Creativo de Marketing DEPA IA. Combinas cuatro roles en una sola voz:
1) Diseñador visual (composición, tipografía, color, formato feed/story/reel).
2) Productor audiovisual (guion, ritmo, hook en 3s, subtítulos, voz en off).
3) Mercadólogo inbound (Attract→Convert→Close→Delight; Entretener→Información→Conexión).
4) Asesor de marca (alineación con tono, audiencia y manual de marca si existe).

Tu trabajo: ayudar al usuario a decidir CÓMO generar el contenido para su negocio/marca
antes de lanzar el pipeline (brief → estrategia → copy → diseño/video).

Reglas de respuesta:
- Responde en español claro, cálido y accionable (salvo que pidan otro idioma).
- Máximo ~180 palabras salvo que pidan detalle.
- Da recomendaciones concretas: formato (feed/story/reel), ángulo, hook, CTA, arquetipo visual.
- Si hay manual de marca, respétalo (tono, claims, colores descritos).
- No inventes métricas ni resultados garantizados.
- No pidas API keys ni datos sensibles.
- Si falta contexto, haz 1–2 preguntas cortas y aún así ofrece una primera recomendación.
""" + inbound_system_addendum(role="advisor")


def _stub_reply(message: str, *, brand_loaded: bool) -> str:
    """Respuesta determinista sin LLM."""
    tip_marca = (
        " Ya tienes manual de marca cargado: úsalo para fijar tono y límites de claims."
        if brand_loaded
        else " Tip: sube el PDF del manual de marca para que el pipeline y yo respetemos tu identidad."
    )
    lower = (message or "").lower()
    if any(k in lower for k in ("reel", "video", "tiktok", "shorts")):
        return (
            "Para video corto: abre con un hook visual en 3s (pregunta o contraste), "
            "estructura Entretener → Información → Conexión, subtítulos grandes y CTA "
            "de comentario/DM. Usa formato reel (9:16) y 15–30s."
            + tip_marca
        )
    if any(k in lower for k in ("story", "historia")):
        return (
            "Para stories: un mensaje por frame, tipografía centrada, CTA simple "
            "(swipe/responder). Prioriza claridad sobre densidad de copy."
            + tip_marca
        )
    if any(k in lower for k in ("linkedin", "b2b", "profesional")):
        return (
            "En LinkedIn: ángulo educativo o insight de industria, copy más largo, "
            "hook en la primera línea, hashtags 3–5 y CTA de conversación. "
            "Visual limpio tipo editorial o infográfico."
            + tip_marca
        )
    return (
        "Define en el brief: qué ofreces (descripción del producto/evento), a quién "
        "hablas y el objetivo (branding, leads, comunidad). Yo te recomiendo formato "
        "(feed/story/reel), hook y CTA; luego lanza Sync/Async en Nuevo Brief."
        + tip_marca
    )


class CreativeAdvisorAgent:
    """Chat de asesoría creativa con contexto de brief + manual de marca."""

    def reply(
        self,
        message: str,
        *,
        tenant_id: str,
        history: list[dict[str, str]] | None = None,
        brief_context: dict | None = None,
    ) -> str:
        text = (message or "").strip()
        if not text:
            return "Cuéntame qué quieres comunicar (producto, evento o campaña) y para quién."

        brand = load_brand_text(tenant_id)
        llm = get_llm()
        if llm is None or not hasattr(llm, "complete_text"):
            logger.warning("advisor.using_stub", reason="no_llm_or_complete_text")
            return _stub_reply(text, brand_loaded=bool(brand))

        user_parts = [
            "Contexto del brief actual (puede estar incompleto):",
            f"- Descripción producto/evento (tema): {(brief_context or {}).get('tema') or '—'}",
            f"- Público: {(brief_context or {}).get('publico_objetivo') or '—'}",
            f"- Red: {(brief_context or {}).get('red_social') or '—'}",
            f"- Objetivo: {(brief_context or {}).get('objetivo') or '—'}",
            f"- Tono: {(brief_context or {}).get('tono_marca') or '—'}",
            f"- Formato pensado: {(brief_context or {}).get('content_format') or '—'}",
        ]
        if brand:
            user_parts.append(
                "\nManual de marca (extracto):\n" + brand[:4000]
            )
        if history:
            user_parts.append("\nHistorial reciente:")
            for turn in history[-8:]:
                role = turn.get("role", "user")
                content = (turn.get("content") or "").strip()
                if content:
                    user_parts.append(f"{role}: {content}")
        user_parts.append(f"\nMensaje del usuario:\n{text}")
        user_prompt = "\n".join(user_parts)

        try:
            return llm.complete_text(_SYSTEM, user_prompt, max_tokens=700).strip()
        except Exception as exc:
            logger.error("advisor.llm_error", error=str(exc))
            return _stub_reply(text, brand_loaded=bool(brand))
