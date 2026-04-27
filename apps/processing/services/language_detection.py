from dataclasses import dataclass
import re

try:
    from langdetect import detect_langs  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    detect_langs = None

AMHARIC_CHAR_PATTERN = re.compile(r"[\u1200-\u137F]")
LATIN_CHAR_PATTERN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class LanguageDetectionResult:
    language_detected: str
    confidence_score: float
    is_mixed_language: bool


class LanguageDetectionService:
    """Detects Amharic versus mixed language content and computes confidence."""

    def detect(self, text: str) -> LanguageDetectionResult:
        normalized_text = text or ""

        if detect_langs is not None:
            try:
                predictions = detect_langs(normalized_text[:5000])
                top_prediction = predictions[0]
                language_code = top_prediction.lang
                confidence = float(top_prediction.prob)
                if language_code.startswith("am"):
                    return LanguageDetectionResult("amharic", confidence, False)
                if "en" in language_code:
                    return LanguageDetectionResult("mixed", confidence * 0.8, True)
                return LanguageDetectionResult(language_code, confidence, False)
            except Exception:
                pass

        amharic_matches = len(AMHARIC_CHAR_PATTERN.findall(normalized_text))
        latin_matches = len(LATIN_CHAR_PATTERN.findall(normalized_text))
        total = amharic_matches + latin_matches
        if total == 0:
            return LanguageDetectionResult("amharic", 0.0, False)

        amharic_ratio = amharic_matches / total
        if amharic_ratio >= 0.6:
            return LanguageDetectionResult("amharic", amharic_ratio, latin_matches > 0)
        if latin_matches > amharic_matches:
            return LanguageDetectionResult("mixed", latin_matches / total, amharic_matches > 0)
        return LanguageDetectionResult("mixed", max(amharic_ratio, latin_matches / total), True)

    def score_confidence(self, text: str) -> float:
        return self.detect(text).confidence_score