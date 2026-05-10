from django.test import TestCase

from apps.nlp.services import NLPTaskCreationService
from apps.nlp.models.nlp_chunk import NLPChunk
from apps.nlp.models.choices import NLPChunkStatusChoices, NLPTaskTypeChoices
from apps.documents.models import RawDocument
from apps.processing.models.chunk import Chunk, ExtractedDocument
from django.utils import timezone
from apps.users.models.user import CustomUser


class NLPTaskCreationServiceTestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(email="u1@example.com", username="u1", full_name="U One")
        raw = RawDocument.objects.create(user=self.user, title="doc")
        extracted = ExtractedDocument.objects.create(raw_document=raw, full_text="text", processed_at=timezone.now())
        chunk = Chunk.objects.create(extracted_document=extracted, text="src", order_index=0, char_start=0, char_end=4, token_count=1)

        # create 35 NLPChunk objects ready for annotation
        for i in range(35):
            NLPChunk.objects.create(
                source_chunk=chunk,
                task_type=NLPTaskTypeChoices.SENTIMENT,
                text=f"sample {i}",
                order_index=i,
                char_start=0,
                char_end=1,
                status=NLPChunkStatusChoices.READY_FOR_ANNOTATION,
            )

    def test_create_tasks_batches_chunks_and_updates_status(self):
        service = NLPTaskCreationService()
        summary = service.create_tasks()

        created_tasks = summary.get("tasks_created", 0)
        self.assertGreaterEqual(created_tasks, 1)

        # all chunks should have been moved to IN_ANNOTATION
        in_annotation = NLPChunk.objects.filter(status=NLPChunkStatusChoices.IN_ANNOTATION).count()
        self.assertEqual(in_annotation, 35)
