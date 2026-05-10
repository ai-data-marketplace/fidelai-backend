from django.test import TestCase

from apps.nlp.services import NLPTaskAssignmentService
from apps.nlp.models.nlp_task import NLPAnnotationTask, NLPTaskChunk
from apps.nlp.models.nlp_chunk import NLPChunk
from apps.nlp.models.choices import NLPChunkStatusChoices, NLPTaskTypeChoices
from apps.users.models.user import CustomUser
from apps.documents.models import RawDocument
from apps.processing.models.chunk import Chunk, ExtractedDocument
from django.utils import timezone


class NLPTaskAssignmentServiceTestCase(TestCase):
    def setUp(self):
        # create annotators
        self.annotators = []
        for i in range(5):
            u = CustomUser.objects.create(email=f"ann{i}@example.com", username=f"ann{i}", full_name=f"Ann {i}", role="annotator", is_verified=True)
            self.annotators.append(u)

        # create source chunk and 10 NLPChunks
        raw_user = CustomUser.objects.create(email="owner@example.com", username="owner", full_name="Owner")
        raw = RawDocument.objects.create(user=raw_user, title="doc")
        extracted = ExtractedDocument.objects.create(raw_document=raw, full_text="text", processed_at=timezone.now())
        src_chunk = Chunk.objects.create(extracted_document=extracted, text="src", order_index=0, char_start=0, char_end=4, token_count=1)

        task = NLPAnnotationTask.objects.create(task_type=NLPTaskTypeChoices.SENTIMENT, name="t1", total_chunks=0)

        for i in range(10):
            c = NLPChunk.objects.create(
                source_chunk=src_chunk,
                task_type=NLPTaskTypeChoices.SENTIMENT,
                text=f"text {i}",
                order_index=i,
                char_start=0,
                char_end=1,
                status=NLPChunkStatusChoices.IN_ANNOTATION,
            )
            NLPTaskChunk.objects.create(task=task, nlp_chunk=c, order_index=i)

    def test_assign_tasks_creates_assignments_up_to_three_per_task(self):
        service = NLPTaskAssignmentService()
        summary = service.assign_tasks()

        # expect at least one task assigned and up to three assignments created
        assignments_created = summary.get("assignments_created", 0)
        self.assertGreaterEqual(assignments_created, 1)
        self.assertLessEqual(assignments_created, 3 * NLPAnnotationTask.objects.count())
