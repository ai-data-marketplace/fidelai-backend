from django.test import TestCase
from rest_framework.test import APIClient
from django.utils import timezone

from apps.users.models.user import CustomUser
from apps.documents.models import RawDocument
from apps.processing.models.chunk import ExtractedDocument, Chunk
from apps.nlp.models import (
    NLPAnnotationTask,
    NLPTaskChunk,
    NLPChunk,
    NLPTaskAssignment,
)
from apps.nlp.models.choices import NLPTaskTypeChoices, NLPChunkStatusChoices


class NLPApiEndpointTestCase(TestCase):
    def setUp(self):
        # users
        self.creator = CustomUser.objects.create(email="creator@example.com", username="creator", full_name="Creator")
        self.annotator = CustomUser.objects.create(email="ann@example.com", username="ann", full_name="Ann", role="annotator", is_verified=True)

        # source document + chunk
        raw = RawDocument.objects.create(user=self.creator, title="doc")
        extracted = ExtractedDocument.objects.create(raw_document=raw, full_text="text", processed_at=timezone.now())
        src_chunk = Chunk.objects.create(extracted_document=extracted, text="src", order_index=0, char_start=0, char_end=4, token_count=1)

        # NLP chunk + task
        self.task = NLPAnnotationTask.objects.create(task_type=NLPTaskTypeChoices.SENTIMENT, name="t1", total_chunks=1, created_by=self.creator)
        self.nlp_chunk = NLPChunk.objects.create(
            source_chunk=src_chunk,
            task_type=NLPTaskTypeChoices.SENTIMENT,
            text="some text",
            order_index=0,
            char_start=0,
            char_end=4,
            status=NLPChunkStatusChoices.READY_FOR_ANNOTATION,
        )
        NLPTaskChunk.objects.create(task=self.task, nlp_chunk=self.nlp_chunk, order_index=0)

        # assignment assigned to annotator
        self.assignment = NLPTaskAssignment.objects.create(task=self.task, annotator=self.annotator)

        self.client = APIClient()

    def test_task_list_and_detail(self):
        self.client.force_authenticate(user=self.annotator)
        resp = self.client.get("/api/nlp/tasks/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(str(self.task.id) == t.get("task_id") or t.get("task_id") == str(self.task.id) for t in resp.data))

        # detail
        resp = self.client.get(f"/api/nlp/tasks/{self.task.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("chunks", resp.data)
        self.assertIsInstance(resp.data["chunks"], list)
        self.assertEqual(resp.data["chunks"][0]["text"], self.nlp_chunk.text)

    def test_accept_and_decline(self):
        self.client.force_authenticate(user=self.annotator)

        # accept
        resp = self.client.post(f"/api/nlp/tasks/{self.task.id}/accept/", data={})
        self.assertEqual(resp.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "accepted")

        # decline - first re-create an assignment in assigned state
        self.assignment.status = "assigned"
        self.assignment.save()
        resp = self.client.post(f"/api/nlp/tasks/{self.task.id}/decline/", data={})
        self.assertEqual(resp.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "declined")

    def test_progress_and_annotate_validation(self):
        self.client.force_authenticate(user=self.annotator)

        # ensure accepted for annotation
        self.assignment.status = "accepted"
        self.assignment.save()

        # progress
        resp = self.client.get(f"/api/nlp/tasks/{self.task.id}/progress/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("total_chunks", resp.data)

        # annotate with invalid payload (missing sentiment key)
        bad_payload = {
            "labels": {"not_sentiment": "positive"},
            "confidence_score": 0.9,
            "time_spent_seconds": 10,
        }
        resp = self.client.post(f"/api/nlp/chunks/{self.nlp_chunk.id}/annotate/", data=bad_payload, format="json")
        self.assertEqual(resp.status_code, 400)

        # annotate with valid payload
        good_payload = {
            "labels": {"sentiment": "positive"},
            "confidence_score": 0.9,
            "time_spent_seconds": 12,
        }
        resp = self.client.post(f"/api/nlp/chunks/{self.nlp_chunk.id}/annotate/", data=good_payload, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_chunk_becomes_consensus_ready_when_all_assignees_submit(self):
        annotator_two = CustomUser.objects.create(
            email="ann2@example.com",
            username="ann2",
            full_name="Ann 2",
            role="annotator",
            is_verified=True,
        )
        annotator_three = CustomUser.objects.create(
            email="ann3@example.com",
            username="ann3",
            full_name="Ann 3",
            role="annotator",
            is_verified=True,
        )

        NLPTaskAssignment.objects.create(task=self.task, annotator=annotator_two, status="accepted")
        NLPTaskAssignment.objects.create(task=self.task, annotator=annotator_three, status="accepted")

        self.assignment.status = "accepted"
        self.assignment.save(update_fields=["status"])

        payload = {
            "labels": {"sentiment": "positive"},
            "confidence_score": 0.91,
            "time_spent_seconds": 14,
        }

        for user in (self.annotator, annotator_two, annotator_three):
            self.client.force_authenticate(user=user)
            resp = self.client.post(f"/api/nlp/chunks/{self.nlp_chunk.id}/annotate/", data=payload, format="json")
            self.assertEqual(resp.status_code, 201)

        self.nlp_chunk.refresh_from_db()
        self.assertEqual(self.nlp_chunk.status, NLPChunkStatusChoices.CONSENSUS_READY)
