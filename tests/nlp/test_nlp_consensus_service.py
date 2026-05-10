from django.test import TestCase

from apps.nlp.services import NLPConsensusService
from apps.nlp.models.nlp_consensus import NLPConsensus
from apps.nlp.models.nlp_chunk import NLPChunk
from apps.nlp.models.nlp_annotation import NLPAnnotation, NLPTaskAssignment
from apps.nlp.models.nlp_task import NLPAnnotationTask, NLPTaskChunk
from apps.nlp.models.choices import NLPChunkStatusChoices, NLPTaskTypeChoices
from apps.users.models.user import CustomUser
from apps.documents.models import RawDocument
from apps.processing.models.chunk import Chunk, ExtractedDocument
from django.utils import timezone


class NLPConsensusServiceTestCase(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create(email="owner2@example.com", username="owner2", full_name="Owner2")
        raw = RawDocument.objects.create(user=self.owner, title="doc2")
        extracted = ExtractedDocument.objects.create(raw_document=raw, full_text="text", processed_at=timezone.now())
        src_chunk = Chunk.objects.create(extracted_document=extracted, text="src", order_index=0, char_start=0, char_end=4, token_count=1)

        self.nlp_chunk = NLPChunk.objects.create(
            source_chunk=src_chunk,
            task_type=NLPTaskTypeChoices.SENTIMENT,
            text="I like this",
            order_index=0,
            char_start=0,
            char_end=10,
            status=NLPChunkStatusChoices.CONSENSUS_READY,
        )

        # create a task and assignments for annotators so annotations can reference them
        task = NLPAnnotationTask.objects.create(task_type=NLPTaskTypeChoices.SENTIMENT, name="consensus_task", total_chunks=1)
        NLPTaskChunk.objects.create(task=task, nlp_chunk=self.nlp_chunk, order_index=0)

        self.annotators = []
        for i in range(3):
            u = CustomUser.objects.create(email=f"cann{i}@example.com", username=f"cann{i}", full_name=f"CAnn {i}", role="annotator", is_verified=True)
            self.annotators.append(u)
            NLPTaskAssignment.objects.create(task=task, annotator=u)

        # create three agreeing annotations (positive)
        for u in self.annotators:
            NLPAnnotation.objects.create(
                nlp_chunk=self.nlp_chunk,
                annotator=u,
                task_assignment=NLPTaskAssignment.objects.filter(annotator=u).first(),
                task_type=NLPTaskTypeChoices.SENTIMENT,
                labels={"sentiment": "positive"},
                confidence_score=0.9,
            )

    def test_consensus_creates_approved_consensus_for_unanimous_votes(self):
        service = NLPConsensusService()
        summary = service.run(batch_size=10)

        consensus = NLPConsensus.objects.filter(nlp_chunk=self.nlp_chunk).first()
        self.assertIsNotNone(consensus)
        self.assertEqual(consensus.final_labels.get("sentiment"), "positive")
        self.assertGreaterEqual(float(consensus.agreement_score), 0.7)
        self.nlp_chunk.refresh_from_db()
        self.assertEqual(self.nlp_chunk.status, NLPChunkStatusChoices.APPROVED)
