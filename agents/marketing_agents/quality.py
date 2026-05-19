"""Guardián de calidad / compliance sobre el texto del copy."""

from pydantic import BaseModel


class QualityReview(BaseModel):
    """Resultado del control de calidad: si aprueba y lista de motivos de rechazo."""

    approved: bool
    reasons: list[str]


class ContentQualityGuard:
    """Reglas ligeras de compliance (palabras prohibidas y coherencia de tono)."""

    banned_words = {"estafa", "fake", "garantizado 100%"}

    def validate(self, copy_text: str, brand_tone: str) -> QualityReview:
        """Evalúa el copy frente a palabras bloqueadas y heurísticas de tono formal."""
        lowered = copy_text.lower()
        reasons: list[str] = []
        for word in self.banned_words:
            if word in lowered:
                reasons.append(f"Contiene palabra bloqueada: {word}")

        if brand_tone.lower().startswith("formal") and "!!!" in copy_text:
            reasons.append("Tono formal incompatible con exceso de exclamaciones")

        return QualityReview(approved=not reasons, reasons=reasons)
