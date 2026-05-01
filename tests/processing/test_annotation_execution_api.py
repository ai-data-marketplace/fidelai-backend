from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.documents.models import RawDocument
from apps.processing.models import (
    Annotation,
    AnnotationTask,
    Chunk,
    ConfidenceChoices,
    DomainMatchChoices,
    ExtractedDocument,
    ReadabilityChoices,
    SafetyChoices,
    TaskAssignment,
    TaskAssignmentStatusChoices,
    TaskChunk,
)
from apps.users.models import CustomUser, RoleChoices


class AnnotationExecutionAPITests(APITestCase):
    def setUp(self):
        self.annotator = CustomUser.objects.create_user(
            email="annotator@example.com",
            username="annotator",
            full_name="Annotator User",
            password="password123",
            role=RoleChoices.ANNOTATOR,
            is_verified=True,
        )
        self.other_annotator = CustomUser.objects.create_user(
            email="other@example.com",
            username="other",
            full_name="Other Annotator",
            password="password123",
            role=RoleChoices.ANNOTATOR,
            is_verified=True,
        )
        self.document_owner = CustomUser.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Owner User",
            password="password123",
        )

        self.task, self.assignment, self.chunks = self._build_task_fixture()

    def _build_task_fixture(self):
        raw_document = RawDocument.objects.create(
            user=self.document_owner,
            title="Test Document",
            description="Fixture document",
            domain="other",
            language="amharic",
            consent_given=True,
        )
        extracted_document = ExtractedDocument.objects.create(
            raw_document=raw_document,
            full_text="chunk one chunk two",
            structure=[],
            layout_metadata={},
            language_detected="amharic",
            confidence_score=1,
            processed_at=timezone.now(),
        )
        chunk_one = Chunk.objects.create(
            extracted_document=extracted_document,
            text="chunk one",
            order_index=0,
            char_start=0,
            char_end=9,
            token_count=2,
            metadata={"segment": 1},
        )
        chunk_two = Chunk.objects.create(
            extracted_document=extracted_document,
            text="chunk two",
            order_index=1,
            char_start=10,
            char_end=19,
            token_count=2,
            metadata={"segment": 2},
        )
        task = AnnotationTask.objects.create(
            name="Annotation Task",
            extracted_document=extracted_document,
            domain="other",
            description="Annotate the chunks",
            created_by=self.document_owner,
            total_chunks=2,
        )
        TaskChunk.objects.create(task=task, chunk=chunk_one, order_index=0)
        TaskChunk.objects.create(task=task, chunk=chunk_two, order_index=1)
        assignment = TaskAssignment.objects.create(task=task, annotator=self.annotator, status=TaskAssignmentStatusChoices.ASSIGNED)
        return task, assignment, [chunk_one, chunk_two]

    def test_assignment_lifecycle_and_auto_complete(self):
        self.client.force_authenticate(user=self.annotator)

        response = self.client.post(f"/api/processing/assignments/{self.assignment.id}/accept/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, TaskAssignmentStatusChoices.ACCEPTED)
        self.assertIsNotNone(self.assignment.started_at)

        response = self.client.get(f"/api/processing/assignments/{self.assignment.id}/chunks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertFalse(response.data[0]["annotation_exists"])

        payload = {
            "task_assignment": str(self.assignment.id),
            "domain_match": DomainMatchChoices.MATCH,
            "is_amharic": True,
            "readability": ReadabilityChoices.HIGH,
            "safety_label": SafetyChoices.SAFE,
            "confidence": ConfidenceChoices.HIGH,
            "notes": "first chunk",
            "time_spent_seconds": 12,
            "is_skipped": False,
        }
        response = self.client.post(f"/api/processing/chunks/{self.chunks[0].id}/annotate/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, TaskAssignmentStatusChoices.IN_PROGRESS)

        response = self.client.get(f"/api/processing/assignments/{self.assignment.id}/progress/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["completed_annotations"], 1)
        self.assertEqual(response.data["remaining_chunks"], 1)

        payload["notes"] = "second chunk"
        response = self.client.post(f"/api/processing/chunks/{self.chunks[1].id}/annotate/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, TaskAssignmentStatusChoices.SUBMITTED)
        self.assertIsNotNone(self.assignment.completed_at)

        response = self.client.get("/api/processing/my-assignments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["progress_percentage"], 100)

    def test_duplicate_annotation_and_foreign_access_are_blocked(self):
        self.client.force_authenticate(user=self.annotator)
        self.client.post(f"/api/processing/assignments/{self.assignment.id}/accept/")

        payload = {
            "task_assignment": str(self.assignment.id),
            "domain_match": DomainMatchChoices.MATCH,
            "is_amharic": True,
            "readability": ReadabilityChoices.HIGH,
            "safety_label": SafetyChoices.SAFE,
            "confidence": ConfidenceChoices.HIGH,
            "notes": "first chunk",
            "time_spent_seconds": 12,
            "is_skipped": False,
        }
        response = self.client.post(f"/api/processing/chunks/{self.chunks[0].id}/annotate/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(f"/api/processing/chunks/{self.chunks[0].id}/annotate/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data["detail"][0]), "You have already annotated this chunk.")

        self.client.force_authenticate(user=self.other_annotator)
        response = self.client.post(f"/api/processing/assignments/{self.assignment.id}/accept/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_decline_then_accept_rejected_and_assignment_visibility_filtered(self):
        self.client.force_authenticate(user=self.annotator)
        response = self.client.post(f"/api/processing/assignments/{self.assignment.id}/decline/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(f"/api/processing/assignments/{self.assignment.id}/accept/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get("/api/processing/my-assignments/?status=declined")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)