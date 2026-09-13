"""Helpers de prompt visual: revisión humana, tipografía Pillow y personas en escena."""

from __future__ import annotations

import re
from dataclasses import dataclass


# Tokens de escena real (foto). NO incluir "cambia/cambiar" sueltos: disparaban
# falso positivo con "cambia la tipografía" y metían DEFAULT_SCENE_EDIT (personas).
_SCENE_NOUN_RE = re.compile(
    r"\b("
    r"persona|personas|gente|humano|humanos|pareja|parejas|cliente|clientes|"
    r"sentad[oa]s?|silla|sillas|mesa|mesas|fondo|escena|ambiente|objeto|objetos|"
    r"flor|flores|luz|luces|decoraci[oó]n|mobiliario|"
    r"people|person|couple|sitting|chair|chairs|table|scene|background|props?"
    r")\b",
    re.IGNORECASE,
)

_SCENE_VERB_RE = re.compile(
    r"\b("
    r"agrega|a[nñ]ade|incluye|pon|poner|quita|quitar|reemplaza|reemplazar|"
    r"add|remove|replace"
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

_TYPOGRAPHY_RE = re.compile(
    r"\b("
    r"tipograf[ií]a|tipografico|tipogr[aá]fica|fuente|fuentes|font|fonts|"
    r"letra|letras|lettering|typeface|sans[\s-]?serif|serif|script|cursiva|"
    r"caligr[aá]fica|manuscrita|negrita|bold|italic|"
    r"montserrat|poppins|playfair|bebas|raleway|nunito|rubik|barlow|"
    r"great[\s-]?vibes|roboto|inter|"
    r"tama[nñ]o\s+del?\s+texto|texto\s+m[aá]s\s+(grande|peque[nñ]o)|"
    r"headline\s+(m[aá]s\s+)?(grande|peque[nñ]o|blanco|negro)|"
    r"color\s+del?\s+(texto|tipograf|fuente|letra)|"
    r"contraste\s+(del?\s+)?(texto|tipograf)|"
    r"overlay|may[uú]sculas|min[uú]sculas"
    r")\b",
    re.IGNORECASE,
)

_COPY_RE = re.compile(
    r"\b("
    r"headline|titular|t[ií]tulo|subtitulo|subt[ií]tulo|subline|copy|caption|"
    r"cta|llamado|hashtag|texto\s+del\s+(post|caption|overlay)|"
    r"cambia\s+el\s+texto|reescribe|redact"
    r")\b",
    re.IGNORECASE,
)

_FAMILY_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bmontserrat\b", re.I), "montserrat"),
    (re.compile(r"\bpoppins\b", re.I), "poppins"),
    (re.compile(r"\bplayfair\b", re.I), "playfair"),
    (re.compile(r"\bbebas\b", re.I), "bebas"),
    (re.compile(r"\braleway\b", re.I), "raleway"),
    (re.compile(r"\bnunito\b", re.I), "nunito"),
    (re.compile(r"\brubik\b", re.I), "rubik"),
    (re.compile(r"\bbarlow\b", re.I), "barlow"),
    (re.compile(r"\bgreat[\s-]?vibes\b", re.I), "script_campaign"),
    (re.compile(r"\bscript_campaign\b", re.I), "script_campaign"),
]


@dataclass(frozen=True)
class TypographyRevision:
    """Directivas tipográficas extraídas de las notas HITL (aplicadas con Pillow)."""

    requested: bool = False
    style: str | None = None  # sans | serif | script | display
    family_id: str | None = None
    text_color_hex: str | None = None
    size_scale: float = 1.0
    force_uppercase: bool | None = None
    high_contrast: bool = False


def revision_requests_typography(notes: str | None) -> bool:
    """True si las notas piden cambiar tipografía / color / tamaño del overlay."""
    return bool(_TYPOGRAPHY_RE.search(notes or ""))


def revision_requests_copy_change(notes: str | None) -> bool:
    """True si las notas piden reescribir headline/caption/CTA."""
    return bool(_COPY_RE.search(notes or ""))


def revision_requests_people(notes: str | None) -> bool:
    """True si las notas piden personas / pareja en la escena."""
    return bool(_PEOPLE_RE.search(notes or ""))


def revision_requests_scene_change(notes: str | None) -> bool:
    """True si las notas piden cambiar el contenido fotográfico (no solo tipografía).

    «Cambia la tipografía» NO cuenta como escena. Hace falta un sustantivo de escena
    o un verbo de edición + sustantivo de escena.
    """
    text = notes or ""
    if not text.strip():
        return False
    if revision_requests_typography(text) and not _SCENE_NOUN_RE.search(text):
        return False
    if _SCENE_NOUN_RE.search(text):
        return True
    # Verbo de edición sin sustantivo tipográfico → escena ambigua (p.ej. "agrega algo")
    if _SCENE_VERB_RE.search(text) and not revision_requests_typography(text):
        return True
    return False


def parse_typography_revision(notes: str | None) -> TypographyRevision:
    """Extrae estilo, familia, color y escala desde notas en español/inglés."""
    text = (notes or "").strip()
    if not text or not revision_requests_typography(text):
        return TypographyRevision()

    low = text.lower()
    style: str | None = None
    if re.search(r"\b(script|cursiva|caligr[aá]fica|manuscrita|great[\s-]?vibes)\b", low):
        style = "script"
    elif re.search(r"\b(sans[\s-]?serif|sans|moderna|limpia|minimal|montserrat|poppins)\b", low):
        style = "sans"
    elif re.search(r"\b(display|bebas|impact|poster)\b", low):
        style = "display"
    elif re.search(r"\b(serif|elegante|cl[aá]sica|playfair)\b", low):
        style = "serif"

    family_id: str | None = None
    for pat, fid in _FAMILY_ALIASES:
        if pat.search(text):
            family_id = fid
            break

    text_color_hex: str | None = None
    hex_m = re.search(r"#([0-9a-fA-F]{6})\b", text)
    if hex_m:
        text_color_hex = f"#{hex_m.group(1).upper()}"
    elif re.search(r"\b(blanco|white|claro)\b", low):
        text_color_hex = "#FFFFFF"
    elif re.search(r"\b(negro|black|oscuro)\b", low) and re.search(
        r"\b(texto|tipograf|fuente|letra|headline|color)\b", low
    ):
        text_color_hex = "#0F172A"
    elif re.search(r"\b(dorado|gold|amarillo)\b", low):
        text_color_hex = "#C9A227"

    size_scale = 1.0
    if re.search(r"\b(m[aá]s\s+grande|agranda|larger|bigger|aumenta\s+(el\s+)?tama[nñ]o)\b", low):
        size_scale = 1.22
    elif re.search(r"\b(m[aá]s\s+peque[nñ]a|redu[cz]|smaller|disminuye\s+(el\s+)?tama[nñ]o)\b", low):
        size_scale = 0.82

    force_uppercase: bool | None = None
    if re.search(r"\b(may[uú]sculas|uppercase|todo\s+en\s+may[uú]scula)\b", low):
        force_uppercase = True
    elif re.search(r"\b(min[uú]sculas|lowercase|sin\s+may[uú]sculas)\b", low):
        force_uppercase = False

    high_contrast = bool(
        re.search(r"\b(contraste|legible|leerse|se\s+lea|readable)\b", low)
    )

    return TypographyRevision(
        requested=True,
        style=style,
        family_id=family_id,
        text_color_hex=text_color_hex,
        size_scale=size_scale,
        force_uppercase=force_uppercase,
        high_contrast=high_contrast,
    )


def scene_revision_notes(notes: str | None) -> str | None:
    """Notas aptas para el editor de escena (sin peticiones solo-tipográficas)."""
    text = (notes or "").strip()
    if not text:
        return None
    if revision_requests_typography(text) and not revision_requests_scene_change(text):
        return None
    return text


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
    notes = scene_revision_notes(revision_notes) or ""
    instr = (visual_instructions or "").strip()
    # Si las "instrucciones" son solo tipografía, no las mandes al editor de escena.
    if instr and revision_requests_typography(instr) and not revision_requests_scene_change(instr):
        instr = ""

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

    Las notas solo-tipográficas NO van al generador (Pillow las aplica).
    El cliente Venice corta por la cola (`truncate_prompt`).
    """
    from .venice_client import prompt_limit_for_model, truncate_prompt

    trunc = truncate_fn or truncate_prompt
    notes = (revision_notes or "").strip()
    base = (base_prompt or "").strip()

    if not notes:
        return trunc(base, model)

    # Tipografía / copy overlay → no contaminar el prompt de imagen generativa.
    if revision_requests_typography(notes) and not revision_requests_scene_change(notes):
        return trunc(base, model)

    scene_notes = scene_revision_notes(notes) or notes
    if revision_requests_people(scene_notes):
        priority = people_priority_block(scene_notes)
    else:
        priority = f"CRITICAL REVISION (must obey): {scene_notes}"

    limit = max(200, prompt_limit_for_model(model) - 20)
    reserved = min(len(priority) + 8, max(180, limit // 3))
    base_budget = max(120, limit - reserved)
    if len(base) > base_budget:
        base = base[: base_budget - 1].rstrip() + "…"

    composed = f"{priority}\n\n{base}"
    if len(composed) > limit:
        composed = composed[: limit - 1].rstrip() + "…"
    return composed
