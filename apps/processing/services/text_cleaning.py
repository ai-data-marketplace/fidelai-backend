import re
import unicodedata


class TextCleaningService:
    """Normalizes Amharic text, removes OCR noise, and repairs sentence breaks."""

    def normalize_amharic_unicode(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text or "")
        normalized = normalized.replace("\u200b", "").replace("\ufeff", "")
        return normalized

    def clean_ocr_noise(self, text: str) -> str:
        cleaned = text or ""
        cleaned = re.sub(r"(?im)^\s*(page\s+)?\d+\s*$", "", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"(?m)^\s*[-_=]{3,}\s*$", "", cleaned)
        return cleaned.strip()

    def merge_fragments(self, text: str) -> str:
        merged = re.sub(r"-\n(?=\w)", "", text or "")
        merged = re.sub(r"(?<!\n)\n(?!\n)", " ", merged)
        merged = re.sub(r"\s{2,}", " ", merged)
        return merged.strip()