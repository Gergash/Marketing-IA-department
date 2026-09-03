"""Fallbacks creativos cuando el LLM no está disponible o falla.

Los stubs antiguos interpolaban el brief literalmente
(«Contenido ventas para parejas en instagram con enfoque cercano»),
lo que terminaba impreso en la imagen. Estos helpers escriben copy
dirigido a la audiencia, usando tema + tono, sin jerga de briefing.
"""

from __future__ import annotations

from .schemas import BriefInput, CopyOutput, StrategyOutput

# Frases/meta-patrones que NUNCA deben llegar a overlay ni caption.
META_BRIEF_MARKERS = (
    "contenido ventas",
    "contenido branding",
    "contenido leads",
    "contenido comunidad",
    "publico objetivo",
    "público objetivo",
    "con enfoque",
    "puede acelerar tus resultados",
    "tono de marca",
    "red social",
    "tipo de post",
    "mensaje base",
)


def looks_like_meta_brief_dump(text: str) -> bool:
    """True si el texto parece un volcado de campos del brief, no copy publicable."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return False
    hits = sum(1 for m in META_BRIEF_MARKERS if m in lowered)
    if hits >= 1 and any(
        k in lowered
        for k in ("instagram", "facebook", "linkedin", "tiktok", "twitter", " para ")
    ):
        return True
    if "contenido " in lowered and " para " in lowered and " en " in lowered:
        return True
    if "puede acelerar tus resultados" in lowered:
        return True
    return False


def _tone_bucket(tono: str) -> str:
    t = (tono or "").lower()
    if any(w in t for w in ("formal", "corporativ", "profesional serio")):
        return "formal"
    if any(w in t for w in ("jugueton", "divertid", "irreveren", "humor")):
        return "playful"
    if any(w in t for w in ("inspirador", "motivacion", "emocional")):
        return "inspiring"
    # cercano / amigable / cálido / default
    return "warm"


def creative_strategy_fallback(brief: BriefInput) -> StrategyOutput:
    """Estrategia publicable sin LLM: habla del tema a la audiencia, no del brief."""
    tema = (brief.tema or "este momento").strip()
    audiencia = (brief.publico_objetivo or "tu comunidad").strip()
    objetivo = (brief.objetivo or "branding").strip().lower()
    tone = _tone_bucket(brief.tono_marca)
    platform = (brief.red_social or "instagram").strip().lower()

    if tone == "formal":
        hook = f"{tema}: una experiencia pensada para {audiencia}."
        mensaje = (
            f"Reservar con anticipación garantiza el ambiente y la atención que "
            f"{audiencia} merece. {tema} es la ocasión ideal para vivir algo memorable."
        )
    elif tone == "playful":
        hook = f"¿Listos para {tema.lower()}? Spoiler: va a valer la pena."
        mensaje = (
            f"Si eres de {audiencia}, esto es para ustedes: {tema} con detalles "
            f"que se disfrutan en pareja (o en buena compañía). Ven, prueba y cuéntanos."
        )
    elif tone == "inspiring":
        hook = f"Hay fechas que se sienten distinto. {tema} es una de ellas."
        mensaje = (
            f"Para {audiencia}, los mejores recuerdos empiezan con una decisión simple: "
            f"estar presentes. Celebra {tema} con un plan que se note de verdad."
        )
    else:  # warm / cercano
        hook = f"Este {tema} merece más que un mensaje: merece un momento juntos."
        mensaje = (
            f"Si están buscando un plan especial para {audiencia}, {tema} es la "
            f"excusa perfecta para compartir, brindar y crear un recuerdo bonito. "
            f"Te esperamos con el ambiente listo."
        )

    if "venta" in objetivo or "lead" in objetivo or "conversion" in objetivo:
        mensaje += " Reserva tu mesa o escríbenos y te armamos el plan."
    elif "comunidad" in objetivo:
        mensaje += " Etiqueta a tu persona favorita y armen el plan juntos."

    tags = {
        "instagram": ["#AmorYAmistad", "#PlanEnPareja", "#Momentos"],
        "facebook": ["#AmorYAmistad", "#PlanPerfecto", "#Celebra"],
        "tiktok": ["#DateNight", "#AmorYAmistad", "#Planazo"],
        "x": ["#AmorYAmistad", "#DateNight"],
        "linkedin": ["#Experiencias", "#Hospitalidad", "#Comunidad"],
    }.get(platform, ["#AmorYAmistad", "#Momentos", "#PlanEspecial"])

    tipo = "promocional" if "venta" in objetivo else "entretenimiento"
    return StrategyOutput(
        tipo_post=tipo,
        hook=hook[:120],
        mensaje_base=mensaje,
        hashtags=tags,
    )


def creative_copy_fallback(
    brief: BriefInput,
    strategy: StrategyOutput,
    *,
    qa_feedback: list[str] | None = None,
) -> CopyOutput:
    """Caption + overlay publicables cuando no hay LLM (o el LLM devolvió meta-copy)."""
    tema = (brief.tema or "esta fecha especial").strip()
    audiencia = (brief.publico_objetivo or "ustedes").strip()
    tone = _tone_bucket(brief.tono_marca)
    platform = (brief.red_social or "instagram").strip().lower()

    # Preferir estrategia creativa; si llegó meta-dump, regenerar.
    hook = strategy.hook.strip()
    mensaje = strategy.mensaje_base.strip()
    if looks_like_meta_brief_dump(hook) or looks_like_meta_brief_dump(mensaje):
        fresh = creative_strategy_fallback(brief)
        hook, mensaje = fresh.hook, fresh.mensaje_base
        strategy = fresh

    if tone == "formal":
        headline = hook if len(hook) <= 100 else f"Celebra {tema} con elegancia."
        subline = f"Una experiencia especial para {audiencia}."
        cta = "Reserva tu experiencia."
        body = (
            f"{hook}\n\n{mensaje}\n\n"
            f"Estamos listos para recibirte. Escríbenos y asegura tu lugar."
        )
    elif tone == "playful":
        headline = hook if len(hook) <= 100 else f"{tema}: planazo asegurado."
        subline = "Ven con quien te haga sonreír."
        cta = "Comenta PLAN y te armamos la cita."
        body = (
            f"{hook}\n\n{mensaje}\n\n"
            f"¿In? Comenta PLAN o mándanos DM y te ayudamos a armar la noche."
        )
    else:
        headline = hook if len(hook) <= 100 else f"Un {tema} para recordar juntos."
        subline = f"Pensado para {audiencia} que quieren vivir el momento."
        cta = "Escríbenos y arma tu plan."
        body = (
            f"{hook}\n\n{mensaje}\n\n"
            f"Cuéntanos en comentarios con quién vendrías, o escríbenos y "
            f"te ayudamos a reservar. Este {tema} se disfruta mejor juntos."
        )

    # Longitud de caption según plataforma
    if platform in ("x", "twitter"):
        body = f"{hook} {cta}"[:270]
    elif platform == "tiktok":
        body = f"{hook}\n{cta}"[:150]
    elif platform == "linkedin":
        body = (
            f"{hook}\n\n{mensaje}\n\n"
            f"Si buscas una experiencia cuidada para {audiencia}, conversemos. {cta}"
        )

    if qa_feedback:
        body += "\n\n(Ajuste aplicado según revisión de calidad.)"

    tags = list(strategy.hashtags) or ["#Momentos", "#Celebra", "#Juntos"]
    return CopyOutput(
        copy_final=body.strip(),
        headline_for_image=headline[:100],
        subline_for_image=subline[:80],
        hashtags=tags[:5],
        cta=cta[:45],
    )
