from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.documents.models import RawDocument
from apps.processing.models import (
    AIQualityCheck,
    Chunk,
    ChunkStatusChoices,
    ExtractedDocument,
    ExtractedDocumentChunkingStatusChoices,
)
from apps.processing.services.ai_qc_service import AIQualityCheckService
from apps.users.models import CustomUser


class AIQualityCheckServiceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Owner User",
            password="password123",
        )
        self.raw_document = RawDocument.objects.create(
            user=self.user,
            title="QC Doc",
            description="Fixture",
            domain="health",
            language="amharic",
            consent_given=True,
        )
        self.extracted_document = ExtractedDocument.objects.create(
            raw_document=self.raw_document,
            chunking_status=ExtractedDocumentChunkingStatusChoices.CHUNKED,
            full_text="sample text",
            structure=[],
            layout_metadata={},
            language_detected="amharic",
            confidence_score=1,
            processed_at=timezone.now(),
        )

    def _chunk(self, text="clear amharic health text"):
        return Chunk.objects.create(
            extracted_document=self.extracted_document,
            status=ChunkStatusChoices.PENDING,
            text=text,
            order_index=0,
            char_start=0,
            char_end=len(text),
            token_count=max(1, len(text.split())),
            metadata={},
        )

    def _qc_output(self, language=0.95, domain=0.95, readability=0.95):
        return {
            "language": {"label": "Amharic", "confidence": language},
            "domain": {"label": "Health", "confidence": domain},
            "readability": {"label": "Clear", "confidence": readability},
        }

    def _process_with_outputs(self, chunk, qc_output, safety_output):
        service = AIQualityCheckService()
        with patch.object(service, "run_qc_model_inference", return_value=qc_output), patch.object(
            service,
            "run_safety_model_inference",
            return_value=safety_output,
        ):
            service._process_single_chunk(chunk)

    def test_rejects_hate_or_offensive_safety_labels(self):
        chunk = self._chunk()

        self._process_with_outputs(
            chunk,
            self._qc_output(),
            {"label": "hate", "score": 0.52},
        )

        chunk.refresh_from_db()
        self.assertEqual(chunk.status, ChunkStatusChoices.REJECTED)
        check = AIQualityCheck.objects.get(chunk=chunk)
        self.assertEqual(check.predicted_safety, "hate")
        self.assertEqual(check.raw_safety_output, {"label": "hate", "score": 0.52})

    def test_approves_high_confidence_normal_chunks(self):
        chunk = self._chunk()

        self._process_with_outputs(
            chunk,
            self._qc_output(language=0.91, domain=0.92, readability=0.93),
            {"label": "normal", "score": 0.76},
        )

        chunk.refresh_from_db()
        self.assertEqual(chunk.status, ChunkStatusChoices.APPROVED)

    def test_routes_remaining_chunks_to_ai_low_confidence(self):
        chunk = self._chunk()

        self._process_with_outputs(
            chunk,
            self._qc_output(language=0.89, domain=0.95, readability=0.95),
            {"label": "normal", "score": 0.90},
        )

        chunk.refresh_from_db()
        self.assertEqual(chunk.status, ChunkStatusChoices.AI_LOW_CONFIDENCE)
