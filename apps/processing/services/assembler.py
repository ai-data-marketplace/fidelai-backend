from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredDocumentPayload:
    full_text: str
    structure: list[dict[str, Any]]
    layout_metadata: dict[str, Any]
    language_detected: str
    confidence_score: float
    processed_at: Any


class DocumentStructureAssemblerService:
    """Combines extraction and analysis outputs into the final ExtractedDocument payload."""

    def assemble(self, *, full_text, structure, layout_metadata, language_detected, confidence_score, processed_at):
        return StructuredDocumentPayload(
            full_text=full_text,
            structure=structure,
            layout_metadata=layout_metadata,
            language_detected=language_detected,
            confidence_score=confidence_score,
            processed_at=processed_at,
        )