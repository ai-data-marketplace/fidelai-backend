from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from django.db import IntegrityError, transaction

from apps.processing.models import Chunk, ChunkStatusChoices, ExtractedDocument

from .planning import estimate_tokens
from .types import ChunkSpan, PIPELINE_VERSION


class ChunkPersistenceEngine:
    def persist_chunks(self, *, extracted_document: ExtractedDocument, spans: list[ChunkSpan]) -> list[Chunk]:
        if not spans:
            return []

        created: list[Chunk] = []
        try:
            with transaction.atomic():
                if Chunk.objects.filter(extracted_document=extracted_document).exists():
                    return list(Chunk.objects.filter(extracted_document=extracted_document).order_by("order_index"))

                chunk_rows: list[Chunk] = []
                for order_index, span in enumerate(spans):
                    chunk_text = extracted_document.full_text[span.char_start : span.char_end]
                    if not chunk_text.strip():
                        continue

                    metadata = self.build_metadata(extracted_document, span, chunk_text)
                    chunk_rows.append(
                        Chunk(
                            extracted_document=extracted_document,
                            status=ChunkStatusChoices.PENDING,
                            text=chunk_text,
                            order_index=order_index,
                            char_start=span.char_start,
                            char_end=span.char_end,
                            token_count=estimate_tokens(chunk_text),
                            metadata=metadata,
                        )
                    )

                Chunk.objects.bulk_create(chunk_rows)
                created = list(Chunk.objects.filter(extracted_document=extracted_document).order_by("order_index"))

        except IntegrityError:
            return list(Chunk.objects.filter(extracted_document=extracted_document).order_by("order_index"))

        return created

    def build_metadata(
        self,
        extracted_document: ExtractedDocument,
        span: ChunkSpan,
        chunk_text: str,
    ) -> dict[str, Any]:
        block_types = Counter((block.block_type or "").lower() for block in span.source_blocks)
        source_pages = sorted({int(block.page_number) for block in span.source_blocks})

        layout = extracted_document.layout_metadata or {}
        file_hash = layout.get("file_hash")
        ocr_fallback_used = bool(layout.get("ocr_fallback_used", False))
        quality = layout.get("text_layer_quality") or {}

        content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
        return {
            "pipeline_version": PIPELINE_VERSION,
            "mapping": {
                "method": span.mapping_method,
                "quality": round(float(span.mapping_quality), 4),
                "source_pages": source_pages,
                "source_blocks": [block.ref for block in span.source_blocks[:200]],
            },
            "stats": {
                "block_type_counts": dict(block_types),
                "estimated_tokens": estimate_tokens(chunk_text),
                "char_len": len(chunk_text),
            },
            "document": {
                "language_detected": extracted_document.language_detected,
                "file_hash": file_hash,
                "ocr_fallback_used": ocr_fallback_used,
                "text_layer_quality": quality,
            },
            "content_hash": content_hash,
        }
