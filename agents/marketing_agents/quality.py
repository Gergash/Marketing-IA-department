from pydantic import BaseModel


class QualityReview(BaseModel):
    approved: bool
    reasons: list[str]


class ContentQualityGuard:
    banned_words = {"estafa", "fake", "garantizado 100%"}

    def validate(self, copy_text: str, brand_tone: str) -> QualityReview:
        lowered = copy_text.lower()
        reasons: list[str] = []
        for word in self.banned_words:
            if word in lowered:
                reasons.append(f"Contiene palabra bloqueada: {word}")

        if brand_tone.lower().startswith("formal") and "!!!" in copy_text:
            reasons.append("Tono formal incompatible con exceso de exclamaciones")

        return QualityReview(approved=not reasons, reasons=reasons)
# hacer un retorno de set de palabras encontradas en el string para validar si contiene alguna de las palabras bloqueadas
#lass ContentQualityGuard:
#   banned_words = {"estafa", "fake", "garantizado 100%"}
#   def validate(self, Self_string_to_validate: str) -> set[str]:
#       return set(self.banned_words).intersection(Self_string_to_validate.lower()).union({word for word in Self_string_to_validate.lower() if word in self.banned_words})
