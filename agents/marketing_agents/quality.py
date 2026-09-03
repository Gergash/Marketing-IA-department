"""Guardián de calidad / compliance sobre el texto del copy."""

import re

from pydantic import BaseModel

from .creative_fallback import looks_like_meta_brief_dump


class QualityReview(BaseModel):
    """Resultado del control de calidad: si aprueba y lista de motivos de rechazo."""

    approved: bool
    reasons: list[str]


class ContentQualityGuard:
    """Reglas ligeras de compliance (palabras prohibidas, meta-copy y coherencia de tono)."""

    banned_words = {"estafa", "fake", "garantizado 100%"}

    def validate(
        self,
        copy_text: str,
        brand_tone: str,
        *,
        overlay_headline: str = "",
        overlay_subline: str = "",
    ) -> QualityReview:
        """Evalúa el copy frente a palabras bloqueadas, meta-dump del brief y tono."""
        lowered = copy_text.lower()
        reasons: list[str] = []
        for word in self.banned_words:
            if word in lowered:
                reasons.append(f"Contiene palabra bloqueada: {word}")

        if brand_tone.lower().startswith("formal") and "!!!" in copy_text:
            reasons.append("Tono formal incompatible con exceso de exclamaciones")

        # Rechazar volcados literales del brief (bug histórico del stub / modelos literales)
        for label, fragment in (
            ("caption", copy_text),
            ("headline de imagen", overlay_headline),
            ("subline de imagen", overlay_subline),
        ):
            if looks_like_meta_brief_dump(fragment or ""):
                reasons.append(
                    f"El {label} parece un resumen interno del brief "
                    f"(público/objetivo/tono/plataforma). Reescribe copy creativo "
                    f"dirigido a la audiencia, sin nombrar esos campos."
                )

        if len((copy_text or "").strip()) < 80:
            reasons.append(
                "El caption es demasiado corto; escribe un texto completo con "
                "gancho, cuerpo y CTA alineados al tono."
            )

        headline = (overlay_headline or "").strip()
        if headline:
            if headline.endswith(("…", "...")) and len(headline) > 20:
                reasons.append("Headline de imagen parece truncado; usar oraciones completas")
            if re.search(r"\w{2,}\s*$", headline) and headline[-1].isalpha():
                last_word = headline.split()[-1] if headline.split() else ""
                if len(last_word) <= 4 and last_word.lower() not in {
                    "con",
                    "por",
                    "para",
                    "más",
                    "muy",
                    "del",
                    "los",
                    "las",
                    "una",
                    "uno",
                }:
                    reasons.append(f"Posible palabra incompleta en headline de imagen: '{last_word}'")

        return QualityReview(approved=not reasons, reasons=reasons)
