"""Agente que responde DMs de Instagram/Messenger con tono humano y recoge datos del contacto.

Pide nombre, teléfono/WhatsApp y ciudad/barrio de forma conversacional (uno a la vez),
registra el motivo del mensaje y deriva a una persona del equipo cuando hace falta.
Si el LLM falla NO hay respuesta de plantilla: se marca `llm_error` y la conversación pasa a humano.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from agents.marketing_agents.llm import get_llm

logger = structlog.get_logger(__name__)

# Límite de Instagram para mensajes de texto (1000); se deja margen
_MAX_REPLY_CHARS = 900

SYSTEM_PROMPT = """Eres quien atiende los mensajes directos (DM) de {brand_name} en Instagram y Facebook Messenger, en Colombia.

CÓMO HABLAS
- Cálido, cercano y natural, como una persona real del equipo. Español colombiano neutro, tuteo respetuoso.
- Mensajes cortos (1 a 3 frases). Nada de listas, ni formatos de formulario, ni lenguaje de robot.
- Máximo un emoji ocasional, solo si encaja.
- Primero responde o reconoce lo que la persona dijo; después, si falta, pide UN solo dato.
- Si la persona pregunta directamente si eres un bot, una IA o una persona, responde con honestidad que eres el asistente virtual de {brand_name} y que alguien del equipo puede continuar si lo prefiere.
- No inventes precios, disponibilidad, horarios ni políticas que no estén en el contexto de la marca. Si no sabes, di que alguien del equipo le confirma.

QUÉ NECESITAS CONSEGUIR (sin interrogar)
1. El motivo del mensaje (qué necesita o por qué escribe).
2. Su nombre.
3. Su teléfono o WhatsApp.
4. Su ciudad o barrio.
Pide los datos que falten de a uno, integrados en la conversación. Si la persona no quiere darlos, no insistas.

PRIVACIDAD (Ley 1581 de 2012, habeas data)
- La PRIMERA vez que pidas un dato personal, menciona de forma natural que lo usarán solo para atenderle y comparte este enlace: {privacy_url}
- Si en "aviso_privacidad_enviado" dice true, no repitas el enlace.

CUÁNDO PASAR A UNA PERSONA (needs_human = true)
- Quejas o molestias serias, temas legales, pagos o reembolsos, solicitudes que requieran una decisión del negocio,
  si la persona pide hablar con alguien, o si no entiendes después de intentarlo.
- En ese caso responde con calidez que alguien del equipo le escribe pronto.

DATOS YA CONOCIDOS DEL CONTACTO (no los vuelvas a pedir):
{known}

CONTEXTO DE LA MARCA:
{brand_context}

Responde SOLO con un objeto JSON válido, sin texto adicional, con estas claves:
{{
  "reply": "mensaje para enviar a la persona",
  "full_name": "nombre si lo dijo en la conversación, si no null",
  "phone": "teléfono/WhatsApp si lo dio, si no null",
  "city": "ciudad o barrio si lo dio, si no null",
  "motive": "motivo del contacto en una frase, si no está claro null",
  "motive_category": "compra | cotizacion | soporte | queja | colaboracion | informacion | otro",
  "asked_for_personal_data": true o false,
  "needs_human": true o false,
  "summary": "resumen de la conversación en una o dos frases para el equipo"
}}"""


def _format_known(contact: dict[str, Any]) -> str:
    labels = {
        "display_name": "nombre de perfil",
        "full_name": "nombre",
        "phone": "teléfono",
        "city": "ciudad/barrio",
        "motive": "motivo",
    }
    lines = [f"- {label}: {contact[key]}" for key, label in labels.items() if contact.get(key)]
    lines.append(f"- aviso_privacidad_enviado: {'true' if contact.get('privacy_notice_sent') else 'false'}")
    return "\n".join(lines)


def _format_history(history: list[dict[str, str]]) -> str:
    return "\n".join(f"{m['role'].upper()}: {m['text']}" for m in history if m.get("text"))


class DmResponderAgent:
    """Genera la siguiente respuesta de la conversación y los datos extraídos."""

    def __init__(self, llm=None) -> None:  # noqa: ANN001
        self.llm = llm if llm is not None else get_llm()

    def run(
        self,
        history: list[dict[str, str]],
        contact: dict[str, Any],
        *,
        brand_name: str,
        brand_context: str = "",
        privacy_url: str = "",
    ) -> dict[str, Any]:
        if self.llm is None:
            logger.warning("dm_responder.llm_error", error="LLM no configurado")
            return {"llm_error": True}

        system = SYSTEM_PROMPT.format(
            brand_name=brand_name,
            privacy_url=privacy_url or "(sin enlace configurado)",
            known=_format_known(contact),
            brand_context=(brand_context or "(sin manual de marca cargado)")[:4000],
        )
        user = (
            "Conversación hasta ahora (MARCA = tus mensajes anteriores):\n"
            f"{_format_history(history)}\n\n"
            "Escribe la siguiente respuesta de la MARCA y devuelve el JSON."
        )
        try:
            data = self.llm.complete_json(system, user, max_tokens=700)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dm_responder.llm_error", error=str(exc))
            return {"llm_error": True}

        reply = data.get("reply") if isinstance(data, dict) else None
        if not isinstance(reply, str) or not reply.strip():
            logger.warning("dm_responder.llm_error", error="respuesta sin 'reply'", raw=json.dumps(data)[:300])
            return {"llm_error": True}

        return self._finalize(data, reply.strip(), contact, privacy_url)

    @staticmethod
    def _finalize(data: dict, reply: str, contact: dict[str, Any], privacy_url: str) -> dict[str, Any]:
        """Garantiza el aviso de privacidad la primera vez que se piden datos y recorta el largo."""
        privacy_included = bool(privacy_url) and privacy_url in reply
        needs_notice = (
            privacy_url
            and not contact.get("privacy_notice_sent")
            and data.get("asked_for_personal_data")
            and not privacy_included
        )
        notice = f"\n\nTus datos los usamos solo para atenderte: {privacy_url}" if needs_notice else ""
        limit = _MAX_REPLY_CHARS - len(notice)
        if len(reply) > limit:
            reply = reply[: limit - 1].rstrip() + "…"
        if notice:
            reply += notice
            privacy_included = True

        result = {k: data.get(k) for k in ("full_name", "phone", "city", "motive", "motive_category", "summary")}
        result.update(
            reply=reply,
            needs_human=bool(data.get("needs_human")),
            privacy_notice_included=privacy_included,
        )
        return result
