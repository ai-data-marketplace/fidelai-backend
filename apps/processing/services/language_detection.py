from dataclasses import dataclass
import re

try:
    from langdetect import detect_langs  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    detect_langs = None

AMHARIC_CHAR_PATTERN = re.compile(r"[\u1200-\u137F]")
LATIN_CHAR_PATTERN = re.compile(r"[A-Za-z]")
LATIN_WORD_PATTERN = re.compile(r"[A-Za-z]{2,}")

# Mixed-language thresholds so a tiny amount of Latin text (e.g. one acronym)
# does not force an "amh+eng" label.
MIN_LATIN_CHAR_RATIO_FOR_MIXED = 0.01
MIN_LATIN_WORDS_FOR_MIXED = 3


def _normalize_lang_code(code: str) -> str:
    code = (code or "").strip().lower()
    if not code:
        return "unknown"
    if code.startswith("am"):
        return "amh"
    if code.startswith("en"):
        return "eng"
    # Keep other detector codes as-is (already short BCP-47/ISO-like).
    return code


def _has_meaningful_latin_presence(text: str, latin_matches: int, total_chars: int) -> bool:
    latin_ratio = (latin_matches / total_chars) if total_chars else 0.0
    latin_words = LATIN_WORD_PATTERN.findall(text)
    return latin_ratio >= MIN_LATIN_CHAR_RATIO_FOR_MIXED or len(latin_words) >= MIN_LATIN_WORDS_FOR_MIXED


@dataclass(frozen=True)
class LanguageDetectionResult:
    language_detected: str
    confidence_score: float
    is_mixed_language: bool


class LanguageDetectionService:
    """Detects Amharic versus mixed language content and computes confidence."""

    def detect(self, text: str) -> LanguageDetectionResult:
        normalized_text = text or ""
        # quick script-based heuristics (prefer Amharic when Ethiopic script is present)
        amharic_matches = len(AMHARIC_CHAR_PATTERN.findall(normalized_text))
        latin_matches = len(LATIN_CHAR_PATTERN.findall(normalized_text))
        total_chars = len(normalized_text)
        ethio_ratio = (amharic_matches / total_chars) if total_chars else 0.0
        has_latin_presence = _has_meaningful_latin_presence(normalized_text, latin_matches, total_chars)

        # If we see Ethiopic script above a small threshold, prefer Amharic immediately.
        # This avoids false positives from statistical detectors on mixed or short inputs.
        if ethio_ratio >= 0.02:
            # confidence is a heuristic: prefer a high baseline but allow ratio to influence.
            confidence = max(0.9, min(0.995, ethio_ratio + 0.9))
            language = "amh+eng" if has_latin_presence else "amh"
            return LanguageDetectionResult(language, confidence, has_latin_presence)

        if detect_langs is not None:
            try:
                predictions = detect_langs(normalized_text[:5000])
                top_prediction = predictions[0]
                language_code = top_prediction.lang
                confidence = float(top_prediction.prob)

                # Build composite labels from likely predictions (e.g., "amh+eng").
                likely_codes = []
                for pred in predictions[:3]:
                    pred_code = _normalize_lang_code(pred.lang)
                    if float(pred.prob) >= 0.15 and pred_code not in likely_codes:
                        likely_codes.append(pred_code)

                if not likely_codes:
                    likely_codes = [_normalize_lang_code(language_code)]

                # Script evidence can force/include Amharic for mixed-script text.
                if ethio_ratio >= 0.02 and "amh" not in likely_codes:
                    likely_codes.insert(0, "amh")

                if has_latin_presence and "eng" not in likely_codes and "amh" in likely_codes:
                    likely_codes.append("eng")

                is_mixed = len(likely_codes) > 1
                language_label = "+".join(likely_codes) if is_mixed else likely_codes[0]
                if language_label == "unknown":
                    language_label = "amh" if ethio_ratio >= 0.02 else "eng"
                adjusted_confidence = confidence * 0.8 if is_mixed else confidence
                return LanguageDetectionResult(language_label, adjusted_confidence, is_mixed)
            except Exception:
                pass
        # Fallback: script/latin character counting when statistical detector unavailable
        total = amharic_matches + latin_matches
        if total == 0:
            return LanguageDetectionResult("unknown", 0.0, False)

        amharic_ratio = amharic_matches / total
        if amharic_ratio >= 0.6:
            if has_latin_presence:
                return LanguageDetectionResult("amh+eng", amharic_ratio, True)
            return LanguageDetectionResult("amh", amharic_ratio, False)
        if latin_matches > amharic_matches:
            if amharic_matches > 0:
                if has_latin_presence:
                    return LanguageDetectionResult("amh+eng", latin_matches / total, True)
                return LanguageDetectionResult("amh", amharic_ratio, False)
            return LanguageDetectionResult("eng", latin_matches / total, False)
        if has_latin_presence:
            return LanguageDetectionResult("amh+eng", max(amharic_ratio, latin_matches / total), True)
        return LanguageDetectionResult("amh", amharic_ratio, False)

    def score_confidence(self, text: str) -> float:
        return self.detect(text).confidence_score