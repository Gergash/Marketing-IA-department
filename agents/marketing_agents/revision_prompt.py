"""Helpers de prompt visual: revisión humana y personas en escena."""

from __future__ import annotations

import re

# La revisión pide cambiar el contenido de la foto (no solo el copy overlay).
_SCENE_CHANGE_RE = re.compile(
    r"\b("
    r"persona|personas|gente|humano|humanos|pareja|parejas|cliente|clientes|"
    r"sentad[oa]s?|silla|sillas|mesa|agrega|a[nñ]ade|incluye|pon|poner|"
    r"quita|quita[rd]|cambia|cambiar|reemplaza|fondo|escena|ambiente|"
    r"people|person|couple|sitting|chair|add|remove|change|scene"
    r")\b",
    re.IGNORECASE,
)

_PEOPLE_RE = re.compile(
    r"\b("
    r"persona|personas|gente|humano|humanos|pareja|parejas|"
    r"sentad[oa]s?|people|person|couple|sitting|diners|comensal"
    r")\b",
    re.IGNORECASE,
)


def revision_requests_scene_change(notes: str | None) -> bool:
    """True si las notas piden cambiar el contenido visual, no solo tipografía."""
    return bool(_SCENE_CHANGE_RE.search(notes or ""))


def revision_requests_people(notes: str | None) -> bool:
    """True si las notas piden personas / pareja en la escena."""
    return bool(_PEOPLE_RE.search(notes or ""))


def people_priority_block(notes: str) -> str:
    """Bloque de prioridad alta para que el modelo no ignore la petición de personas."""
    return (
        "CRITICAL SCENE REQUIREMENT (must obey): "
        f"{notes.strip()} "
        "Show realistic people in the scene as requested — for example a couple "
        "actually sitting on the chairs at the table, facing each other, natural poses, "
        "photorealistic humans (not empty chairs). Empty furniture alone is incorrect."
    )


_DEFAULT_SCENE_EDIT = (
    "Add two photorealistic people naturally seated on the empty chairs at the table, "
    "relaxed dinner poses, facing each other or the table, correct scale and lighting. "
    "Empty chairs without people is incorrect."
)

_NO_TYPOGRAPHY_EDIT = (
    "CRITICAL: Do NOT add, redraw, invent, or alter ANY text, letters, words, logos, "
    "watermarks, captions, buttons, or typography. Leave every existing letter/logo "
    "in the photo exactly as-is (do not rewrite or sharpen text). Typography is applied "
    "in a later step — your only job is the photographic scene edit."
)


def build_scene_edit_prompt(
    visual_instructions: str | None = None,
    *,
    revision_notes: str | None = None,
) -> str:
    """Prompt SOLO para /image/edit o img2img sobre foto real.

    Nunca incluye copy de marketing ni instrucciones de tipografía: eso lo hace Pillow.
    Si el modelo recibe headline/CTA, pinta letras ilegibles encima de la foto.
    """
    bits: list[str] = []
    notes = (revision_notes or "").strip()
    instr = (visual_instructions or "").strip()

    if notes and revision_requests_people(notes):
        bits.append(people_priority_block(notes))
    elif notes and revision_requests_scene_change(notes):
        bits.append(f"CRITICAL SCENE EDIT (must obey): {notes}")

    if instr:
        bits.append(f"User scene instructions: {instr}")

    if not bits:
        bits.append(_DEFAULT_SCENE_EDIT)
    elif not (notes and revision_requests_people(notes)) and not revision_requests_people(
        instr
    ):
        # Alter marcado pero sin pedir personas explícitas: aún así priorizar escena útil
        if revision_requests_scene_change(instr) or revision_requests_scene_change(notes):
            pass
        else:
            bits.insert(0, _DEFAULT_SCENE_EDIT)

    bits.append(
        "Keep the real venue, furniture, lighting, rose petals, lanterns and atmosphere "
        "recognizable. Only apply the requested scene changes."
    )
    bits.append(_NO_TYPOGRAPHY_EDIT)
    return " ".join(bits)


def compose_visual_prompt(
    base_prompt: str,
    *,
    model: str,
    revision_notes: str | None = None,
    truncate_fn=None,
) -> str:
    """Arma el prompt final protegiendo las notas de revisión del truncado.

    El cliente Venice corta por la cola (`truncate_prompt`). Si las notas van al final
    de un brief+manual largo, se pierden. Aquí: truncamos la BASE y anexamos la revisión.
    """
    from .venice_client import prompt_limit_for_model, truncate_prompt

    trunc = truncate_fn or truncate_prompt
    notes = (revision_notes or "").strip()
    base = (base_prompt or "").strip()

    if not notes:
        return trunc(base, model)

    if revision_requests_people(notes):
        priority = people_priority_block(notes)
    else:
        priority = f"CRITICAL REVISION (must obey): {notes}"

    # Reservar espacio para la revisión dentro del límite del modelo.
    limit = max(200, prompt_limit_for_model(model) - 20)
    reserved = min(len(priority) + 8, max(180, limit // 3))
    base_budget = max(120, limit - reserved)
    if len(base) > base_budget:
        base = base[: base_budget - 1].rstrip() + "…"

    composed = f"{priority}\n\n{base}"
    # Seguridad final por si priority+base aún exceden
    if len(composed) > limit:
        composed = composed[: limit - 1].rstrip() + "…"
    return composed
