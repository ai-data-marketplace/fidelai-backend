from dataclasses import dataclass
from statistics import mean
from typing import Any

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None


@dataclass(frozen=True)
class OCRPageResult:
    page_number: int
    text: str
    confidence: float
    blocks: list[dict[str, Any]]


class OCRService:
    """Handles scanned PDFs and images using OCR-ready preprocessing."""

    def preprocess_image(self, image_bytes: bytes) -> bytes:
        if cv2 is None or np is None:
            return image_bytes

        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is None:
            return image_bytes

        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(grayscale, None, 25, 7, 21)
        thresholded = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        success, encoded = cv2.imencode(".png", thresholded)
        return encoded.tobytes() if success else image_bytes

    def extract_page_text(self, image_bytes: bytes, page_number: int = 1) -> OCRPageResult:
        if pytesseract is None:
            raise RuntimeError("pytesseract is required for OCR extraction.")

        processed_bytes = self.preprocess_image(image_bytes)
        blocks: list[dict[str, Any]] = []
        confidence_values: list[float] = []

        if cv2 is not None and np is not None:
            image_array = np.frombuffer(processed_bytes, dtype=np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            raw_text = pytesseract.image_to_string(image, lang="amh+eng") if image is not None else ""
            data = pytesseract.image_to_data(image, lang="amh+eng", output_type=pytesseract.Output.DICT) if image is not None else None
        else:
            from io import BytesIO
            from PIL import Image

            image = Image.open(BytesIO(processed_bytes))
            raw_text = pytesseract.image_to_string(image, lang="amh+eng")
            data = pytesseract.image_to_data(image, lang="amh+eng", output_type=pytesseract.Output.DICT)

        if data:
            words = data.get("text", [])
            for index, word in enumerate(words):
                word_text = (word or "").strip()
                if not word_text:
                    continue

                confidence_raw = data.get("conf", [])[index]
                try:
                    confidence_value = float(confidence_raw)
                except Exception:
                    confidence_value = -1.0
                if confidence_value >= 0:
                    confidence_values.append(confidence_value)

                blocks.append(
                    {
                        "type": "text",
                        "text": word_text,
                        "bbox": [
                            data.get("left", [0])[index],
                            data.get("top", [0])[index],
                            data.get("width", [0])[index],
                            data.get("height", [0])[index],
                        ],
                        "confidence": max(0.0, confidence_value),
                    }
                )

        confidence_score = mean(confidence_values) / 100 if confidence_values else 0.0
        return OCRPageResult(page_number=page_number, text=(raw_text or "").strip(), confidence=confidence_score, blocks=blocks)

    def score_confidence(self, extracted_pages: list[OCRPageResult]) -> float:
        scores = [page.confidence for page in extracted_pages if page.confidence is not None]
        return sum(scores) / len(scores) if scores else 0.0