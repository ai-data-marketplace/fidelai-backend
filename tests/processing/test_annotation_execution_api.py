from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.documents.models import RawDocument
from apps.notifications.models import NotificationTemplate, NotificationTypeChoices
from apps.processing.models import (
    Annotation,
    AnnotationTask,
    Chunk,
    ChunkStatusChoices,
    ConfidenceChoices,
    DomainMatchChoices,
    ExtractedDocument,
    ReadabilityChoices,
    SafetyChoices,
    TaskAssignment,
    TaskAssignmentStatusChoices,
    TaskChunk,
)
from apps.scoring.models import ScoreActionTypeChoices, ScoreConfig, ScoreLog, UserScore
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

        ScoreConfig.objects.create(action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED, points_value=5)
        ScoreConfig.objects.create(action_type=ScoreActionTypeChoices.ANNOTATION_MATCH_CONSENSUS, points_value=8)
        ScoreConfig.objects.create(action_type=ScoreActionTypeChoices.ANNOTATION_BELOW_THRESHOLD, points_value=-2)
        UserScore.objects.create(user=self.annotator, total_points=0)
        UserScore.objects.create(user=self.other_annotator, total_points=0)
        NotificationTemplate.objects.create(
            notification_type=NotificationTypeChoices.TASK_ASSIGNED,
            category="tasks",
            title_template="Assigned: {task_name}",
            message_template="Task {task_name} has been assigned.",
            active=True,
        )
        NotificationTemplate.objects.create(
            notification_type=NotificationTypeChoices.TASK_COMPLETED,
            category="tasks",
            title_template="Completed: {task_name}",
            message_template="Task {task_name} was completed.",
            active=True,
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
        self.assertEqual(ScoreLog.objects.filter(user=self.annotator, action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED).count(), 1)
        self.annotator.user_score.refresh_from_db()
        self.assertEqual(self.annotator.user_score.total_points, 5)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, TaskAssignmentStatusChoices.IN_PROGRESS)

        response = self.client.get(f"/api/processing/assignments/{self.assignment.id}/progress/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["completed_annotations"], 1)
        self.assertEqual(response.data["remaining_chunks"], 1)

        payload["notes"] = "second chunk"
        response = self.client.post(f"/api/processing/chunks/{self.chunks[1].id}/annotate/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ScoreLog.objects.filter(user=self.annotator, action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED).count(), 2)
        self.annotator.user_score.refresh_from_db()
        self.assertEqual(self.annotator.user_score.total_points, 10)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, TaskAssignmentStatusChoices.SUBMITTED)
        self.assertIsNotNone(self.assignment.completed_at)

        response = self.client.get("/api/processing/my-assignments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

        response = self.client.get("/api/processing/my-assignments/?status=submitted")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_chunk_status_moves_to_annotated_after_consensus(self):
        third_annotator = CustomUser.objects.create_user(
            email="third@example.com",
            username="third",
            full_name="Third Annotator",
            password="password123",
            role=RoleChoices.ANNOTATOR,
            is_verified=True,
        )
        other_assignment = TaskAssignment.objects.create(
            task=self.task,
            annotator=self.other_annotator,
            status=TaskAssignmentStatusChoices.ASSIGNED,
        )
        third_assignment = TaskAssignment.objects.create(
            task=self.task,
            annotator=third_annotator,
            status=TaskAssignmentStatusChoices.ASSIGNED,
        )

        payload = {
            "domain_match": DomainMatchChoices.MATCH,
            "is_amharic": True,
            "readability": ReadabilityChoices.HIGH,
            "safety_label": SafetyChoices.SAFE,
            "confidence": ConfidenceChoices.HIGH,
            "notes": "consensus annotation",
            "time_spent_seconds": 12,
            "is_skipped": False,
        }

        # First annotator submits: chunk should enter IN_ANNOTATION.
        self.client.force_authenticate(user=self.annotator)
        self.client.post(f"/api/processing/assignments/{self.assignment.id}/accept/")
        response = self.client.post(
            f"/api/processing/chunks/{self.chunks[0].id}/annotate/",
            {**payload, "task_assignment": str(self.assignment.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.chunks[0].refresh_from_db()
        self.assertEqual(self.chunks[0].status, ChunkStatusChoices.IN_ANNOTATION)

        # Second annotator submits: still in progress for chunk consensus.
        self.client.force_authenticate(user=self.other_annotator)
        self.client.post(f"/api/processing/assignments/{other_assignment.id}/accept/")
        response = self.client.post(
            f"/api/processing/chunks/{self.chunks[0].id}/annotate/",
            {**payload, "task_assignment": str(other_assignment.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.chunks[0].refresh_from_db()
        self.assertEqual(self.chunks[0].status, ChunkStatusChoices.IN_ANNOTATION)

        # Third annotator reaches consensus target -> ANNOTATED.
        self.client.force_authenticate(user=third_annotator)
        self.client.post(f"/api/processing/assignments/{third_assignment.id}/accept/")
        response = self.client.post(
            f"/api/processing/chunks/{self.chunks[0].id}/annotate/",
            {**payload, "task_assignment": str(third_assignment.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.chunks[0].refresh_from_db()
        self.assertEqual(self.chunks[0].status, ChunkStatusChoices.ANNOTATED)

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
        first_annotation_id = response.data["annotation_id"]

        # Re-submit with updated notes (simulates going back and modifying)
        payload["notes"] = "updated first chunk"
        response = self.client.post(f"/api/processing/chunks/{self.chunks[0].id}/annotate/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["annotation_id"], first_annotation_id)  # Same annotation, updated
        
        # Verify annotation was updated
        annotation = Annotation.objects.get(pk=first_annotation_id)
        self.assertEqual(annotation.notes, "updated first chunk")

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