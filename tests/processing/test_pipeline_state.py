from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.documents.models import RawDocument
from apps.documents.models import ReviewStatusChoices
from apps.processing.models import (
    AnnotationTask,
    Chunk,
    ChunkStatusChoices,
    ExtractedDocument,
    ExtractedDocumentChunkingStatusChoices,
    TaskChunk,
)
from apps.processing.services.chunking import DocumentChunkingPipelineService
from apps.processing.services.task_creation_service import ChunkingNotCompleteError, TaskCreationService
from apps.scoring.models import ScoreActionTypeChoices, ScoreConfig, ScoreLog, UserScore
from apps.users.models import CustomUser
from apps.users.models.roles import RoleChoices


class ProcessingPipelineStateTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Owner User",
            password="password123",
        )
        self.contributor = CustomUser.objects.create_user(
            email="contributor@example.com",
            username="contributor",
            full_name="Contributor User",
            password="password123",
            role=RoleChoices.CONTRIBUTOR,
            is_verified=True,
        )

        ScoreConfig.objects.create(
            action_type=ScoreActionTypeChoices.DOCUMENT_APPROVED,
            points_value=7,
        )
        UserScore.objects.create(user=self.contributor, total_points=0)

    def _create_extracted_document(self, *, chunking_status=ExtractedDocumentChunkingStatusChoices.PENDING, full_text="alpha beta gamma"):
        raw_document = RawDocument.objects.create(
            user=self.contributor,
            title="Pipeline Doc",
            description="Fixture",
            domain="other",
            language="amharic",
            consent_given=True,
        )
        return ExtractedDocument.objects.create(
            raw_document=raw_document,
            chunking_status=chunking_status,
            full_text=full_text,
            structure=[],
            layout_metadata={},
            language_detected="amharic",
            confidence_score=1,
            processed_at=timezone.now(),
        )

    def test_chunking_marks_raw_document_in_review_then_approved(self):
        extracted_document = self._create_extracted_document()
        service = DocumentChunkingPipelineService()

        fake_span = MagicMock()
        fake_chunk = MagicMock()

        def persist_chunks_side_effect(*, extracted_document, spans):
            extracted_document.raw_document.refresh_from_db()
            self.assertEqual(extracted_document.raw_document.review_status, ReviewStatusChoices.IN_REVIEW)
            return [fake_chunk]

        with patch.object(service._planner, "flatten_structure", return_value=[]), patch.object(
            service._planner,
            "plan_chunk_spans",
            return_value=[fake_span],
        ), patch.object(service._persistence, "persist_chunks", side_effect=persist_chunks_side_effect):
            result = service.chunk(extracted_document)

        self.assertEqual(result, [fake_chunk])
        extracted_document.refresh_from_db()
        self.assertEqual(extracted_document.chunking_status, ExtractedDocumentChunkingStatusChoices.CHUNKED)
        self.assertEqual(extracted_document.raw_document.review_status, ReviewStatusChoices.APPROVED)

    def test_task_creation_uses_only_ai_low_confidence_chunks(self):
        extracted_document = self._create_extracted_document(chunking_status=ExtractedDocumentChunkingStatusChoices.CHUNKED)
        low_confidence_chunk = Chunk.objects.create(
            extracted_document=extracted_document,
            status=ChunkStatusChoices.AI_LOW_CONFIDENCE,
            text="low confidence chunk",
            order_index=0,
            char_start=0,
            char_end=20,
            token_count=3,
            metadata={},
        )
        annotated_chunk = Chunk.objects.create(
            extracted_document=extracted_document,
            status=ChunkStatusChoices.ANNOTATED,
            text="annotated chunk",
            order_index=1,
            char_start=14,
            char_end=29,
            token_count=2,
            metadata={},
        )

        result = TaskCreationService().create_task_for_extracted_document(extracted_document.id)

        self.assertTrue(result["created"])
        task = AnnotationTask.objects.get(extracted_document=extracted_document)
        self.assertEqual(task.total_chunks, 1)
        task_chunk_ids = list(TaskChunk.objects.filter(task=task).values_list("chunk_id", flat=True))
        self.assertEqual(task_chunk_ids, [low_confidence_chunk.id])
        self.assertNotIn(annotated_chunk.id, task_chunk_ids)

    def test_task_creation_rejects_non_chunked_document(self):
        extracted_document = self._create_extracted_document(chunking_status=ExtractedDocumentChunkingStatusChoices.PENDING)
        Chunk.objects.create(
            extracted_document=extracted_document,
            status=ChunkStatusChoices.PENDING,
            text="pending chunk",
            order_index=0,
            char_start=0,
            char_end=13,
            token_count=2,
            metadata={},
        )

        with self.assertRaises(ChunkingNotCompleteError):
            TaskCreationService().create_task_for_extracted_document(extracted_document.id)

    def test_successful_chunking_scores_document_approval_once(self):
        extracted_document = self._create_extracted_document()
        service = DocumentChunkingPipelineService()

        fake_span = MagicMock()
        fake_chunk = MagicMock()

        with patch.object(service._planner, "flatten_structure", return_value=[]), patch.object(
            service._planner,
            "plan_chunk_spans",
            return_value=[fake_span],
        ), patch.object(service._persistence, "persist_chunks", return_value=[fake_chunk]):
            result = service.chunk(extracted_document)

        self.assertEqual(result, [fake_chunk])
        self.assertEqual(
            ScoreLog.objects.filter(
                user=self.contributor,
                action_type=ScoreActionTypeChoices.DOCUMENT_APPROVED,
                document=extracted_document.raw_document,
            ).count(),
            1,
        )
        self.contributor.user_score.refresh_from_db()
        self.assertEqual(self.contributor.user_score.total_points, 7)

        with patch.object(service._planner, "flatten_structure", return_value=[]), patch.object(
            service._planner,
            "plan_chunk_spans",
            return_value=[fake_span],
        ), patch.object(service._persistence, "persist_chunks", return_value=[fake_chunk]):
            service.chunk(extracted_document)

        self.assertEqual(
            ScoreLog.objects.filter(
                user=self.contributor,
                action_type=ScoreActionTypeChoices.DOCUMENT_APPROVED,
                document=extracted_document.raw_document,
            ).count(),
            1,
        )
        self.contributor.user_score.refresh_from_db()
        self.assertEqual(self.contributor.user_score.total_points, 7)
