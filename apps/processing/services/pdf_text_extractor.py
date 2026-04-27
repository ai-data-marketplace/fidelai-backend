from dataclasses import dataclass
from typing import Any

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fitz = None

try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pdfplumber = None


@dataclass(frozen=True)
class PDFPageResult:
    page_number: int
    text: str
    blocks: list[dict[str, Any]]
    confidence: float


class PDFExtractionService:
    """Extracts structured text from digital PDFs while preserving reading order."""

    def extract(self, pdf_bytes: bytes) -> list[PDFPageResult]:
        if fitz is not None:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
            return [self._extract_with_fitz(page) for page in document]

        if pdfplumber is not None:
            from io import BytesIO

            with pdfplumber.open(BytesIO(pdf_bytes)) as document:
                return [self._extract_with_pdfplumber(page, index + 1) for index, page in enumerate(document.pages)]

        raise RuntimeError("Either PyMuPDF (fitz) or pdfplumber must be available for PDF extraction.")

    def _extract_with_fitz(self, page) -> PDFPageResult:
        blocks: list[dict[str, Any]] = []
        text_parts: list[str] = []
        page_data = page.get_text("dict")

        for block in sorted(
            page_data.get("blocks", []),
            key=lambda item: (item.get("bbox", [0, 0, 0, 0])[1], item.get("bbox", [0, 0, 0, 0])[0]),
        ):
            if "lines" not in block:
                continue

            block_text = []
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                if line_text.strip():
                    block_text.append(line_text)

            text_value = " ".join(block_text).strip()
            if text_value:
                blocks.append({"type": "paragraph", "text": text_value, "bbox": block.get("bbox", []), "confidence": 1.0})
                text_parts.append(text_value)

        page_text = "\n".join(text_parts).strip()
        confidence = 1.0 if page_text else 0.0
        return PDFPageResult(page_number=page.number + 1, text=page_text, blocks=blocks, confidence=confidence)

    def _extract_with_pdfplumber(self, page, page_number: int) -> PDFPageResult:
        words = page.extract_words(extra_attrs=["fontname", "size"]) or []
        text = page.extract_text() or ""
        blocks = [
            {
                "type": "word",
                "text": word.get("text", ""),
                "bbox": [word.get("x0"), word.get("top"), word.get("x1"), word.get("bottom")],
                "confidence": 1.0,
            }
            for word in words
            if word.get("text")
        ]
        confidence = 1.0 if text.strip() else 0.0
        return PDFPageResult(page_number=page_number, text=text.strip(), blocks=blocks, confidence=confidence)

    def detect_structure_hints(self, extracted_pages: list[PDFPageResult]) -> list[dict[str, Any]]:
        hints: list[dict[str, Any]] = []
        for page in extracted_pages:
            hints.append(
                {
                    "page": page.page_number,
                    "has_text": bool(page.text.strip()),
                    "block_count": len(page.blocks),
                    "estimated_headers": [block for block in page.blocks if len(str(block.get("text", "")).split()) <= 6],
                }
            )
        return hints


class PDFTextExtractorService(PDFExtractionService):
    """Backward-compatible alias for the PDF extraction service."""