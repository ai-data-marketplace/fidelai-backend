from dataclasses import dataclass
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

try:
    from docx import Document  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Document = None


DOCX_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass(frozen=True)
class DOCXExtractionResult:
    text: str
    blocks: list[dict[str, Any]]
    confidence: float


class DOCXExtractionService:
    """Extracts structured paragraphs, headings, and lists from DOCX files."""

    def extract(self, docx_bytes: bytes) -> DOCXExtractionResult:
        if Document is not None:
            document = Document(BytesIO(docx_bytes))
            blocks: list[dict[str, Any]] = []
            text_parts: list[str] = []

            for paragraph in document.paragraphs:
                paragraph_text = paragraph.text.strip()
                if not paragraph_text:
                    continue

                style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
                block_type = "heading" if style_name.lower().startswith("heading") else "paragraph"
                if style_name and "list" in style_name.lower():
                    block_type = "list_item"

                blocks.append({"type": block_type, "text": paragraph_text, "style": style_name, "confidence": 1.0})
                text_parts.append(paragraph_text)

            return DOCXExtractionResult(text="\n".join(text_parts).strip(), blocks=blocks, confidence=1.0 if text_parts else 0.0)

        return self._extract_via_xml(docx_bytes)

    def _extract_via_xml(self, docx_bytes: bytes) -> DOCXExtractionResult:
        blocks: list[dict[str, Any]] = []
        text_parts: list[str] = []

        with ZipFile(BytesIO(docx_bytes)) as archive:
            xml_bytes = archive.read("word/document.xml")
        root = ET.fromstring(xml_bytes)

        for paragraph in root.findall(".//w:p", DOCX_NAMESPACE):
            texts = [node.text for node in paragraph.findall(".//w:t", DOCX_NAMESPACE) if node.text]
            paragraph_text = "".join(texts).strip()
            if not paragraph_text:
                continue

            blocks.append({"type": "paragraph", "text": paragraph_text, "confidence": 1.0})
            text_parts.append(paragraph_text)

        return DOCXExtractionResult(text="\n".join(text_parts).strip(), blocks=blocks, confidence=1.0 if text_parts else 0.0)