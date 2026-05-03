from __future__ import annotations

from django.db import transaction

from apps.processing.models import Chunk, ExtractedDocument, ExtractedDocumentChunkingStatusChoices

from .persistence import ChunkPersistenceEngine
from .planning import ChunkPlanningEngine
from .types import DEFAULT_MAX_TOKENS, DEFAULT_TARGET_TOKENS


class DocumentChunkingPipelineService:
    """Creates deterministic, traceable `Chunk` rows from an ExtractedDocument.

    Contract:
    - `char_start`/`char_end` must reference indices in `ExtractedDocument.full_text`.
    - `Chunk.text` is always persisted as the exact `full_text[char_start:char_end]` slice.
    - Idempotency: by default this service does not delete/overwrite existing chunks.
    """

    def __init__(self) -> None:
        self._planner = ChunkPlanningEngine()
        self._persistence = ChunkPersistenceEngine()

    def chunk(
        self,
        extracted_document: ExtractedDocument,
        *,
        target_tokens: int = DEFAULT_TARGET_TOKENS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> list[Chunk]:
        if not extracted_document.full_text or not extracted_document.full_text.strip():
            return []

        blocks = self._planner.flatten_structure(extracted_document.structure)
        planned_spans = self._planner.plan_chunk_spans(
            full_text=extracted_document.full_text,
            blocks=blocks,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
        )
        chunks = self._persistence.persist_chunks(extracted_document=extracted_document, spans=planned_spans)

        with transaction.atomic():
            extracted_document = ExtractedDocument.objects.select_for_update().get(pk=extracted_document.pk)
            if extracted_document.chunking_status != ExtractedDocumentChunkingStatusChoices.CHUNKED:
                extracted_document.chunking_status = ExtractedDocumentChunkingStatusChoices.CHUNKED
                extracted_document.save(update_fields=["chunking_status", "updated_at"])

        return chunks
