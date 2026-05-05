from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.documents.models import RawDocument
from apps.notifications.models import NotificationTemplate, NotificationTypeChoices
from apps.processing.models import (
    Chunk,
    ExpertReview,
    ExpertTask,
    ExpertTaskAssignment,
    ExpertTaskChunk,
    ExtractedDocument,
    TaskAssignmentStatusChoices,
)
from apps.users.models.applications import RoleApplication
from apps.users.models.roles import RoleApplicationStatusChoices
from apps.scoring.models import ScoreActionTypeChoices, ScoreConfig, ScoreLog, UserScore
from apps.users.models import CustomUser, RoleChoices


class ExpertReviewAPITests(APITestCase):
    def setUp(self):
        self.expert = CustomUser.objects.create_user(
            email="expert@example.com",
            username="expert",
            full_name="Expert User",
            password="password123",
            role=RoleChoices.EXPERT,
            is_verified=True,
        )
        RoleApplication.objects.create(
            user=self.expert,
            role_applied_for=RoleChoices.EXPERT,
            application_data={},
            status=RoleApplicationStatusChoices.APPROVED,
        )
        self.owner = CustomUser.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Owner User",
            password="password123",
        )

        ScoreConfig.objects.create(action_type=ScoreActionTypeChoices.EXPERT_REVIEW_COMPLETED, points_value=12)
        ScoreConfig.objects.create(action_type=ScoreActionTypeChoices.CONFLICT_RESOLVED, points_value=20)
        UserScore.objects.create(user=self.expert, total_points=0)
        NotificationTemplate.objects.create(
            notification_type=NotificationTypeChoices.TASK_REVIEWED,
            category="system",
            title_template="Reviewed chunk {chunk_id}",
            message_template="Chunk {chunk_id} has been reviewed.",
            active=True,
        )

        self.task, self.assignment, self.chunk = self._build_task_fixture()

    def _build_task_fixture(self):
        raw_document = RawDocument.objects.create(
            user=self.owner,
            title="Expert Task Document",
            description="Fixture document",
            domain="other",
            language="amharic",
            consent_given=True,
        )
        extracted_document = ExtractedDocument.objects.create(
            raw_document=raw_document,
            full_text="expert chunk",
            structure=[],
            layout_metadata={},
            language_detected="amharic",
            confidence_score=1,
            processed_at=timezone.now(),
        )
        chunk = Chunk.objects.create(
            extracted_document=extracted_document,
            text="expert chunk",
            order_index=0,
            char_start=0,
            char_end=12,
            token_count=2,
            metadata={"fixture": True},
        )
        task = ExpertTask.objects.create(name="Expert Task", domain="other", total_chunks=1)
        ExpertTaskChunk.objects.create(expert_task=task, chunk=chunk)
        assignment = ExpertTaskAssignment.objects.create(
            expert_task=task,
            expert=self.expert,
            status=TaskAssignmentStatusChoices.ASSIGNED,
        )
        return task, assignment, chunk

    def test_expert_review_submission_scores_points(self):
        self.client.force_authenticate(user=self.expert)
        self.client.post(f"/api/processing/expert/tasks/{self.assignment.id}/accept/")

        payload = {
            "domain_match": "match",
            "is_amharic": True,
            "readability": "high",
            "safety_label": "safe",
            "confidence": "high",
            "notes": "looks good",
            "resolution_reasoning": "resolved conflict",
            "final_decision": "resolved",
        }

        response = self.client.post(f"/api/processing/expert/chunks/{self.chunk.id}/resolve/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(ScoreLog.objects.filter(user=self.expert, action_type=ScoreActionTypeChoices.EXPERT_REVIEW_COMPLETED).count(), 1)
        self.assertEqual(ScoreLog.objects.filter(user=self.expert, action_type=ScoreActionTypeChoices.CONFLICT_RESOLVED).count(), 1)

        self.expert.user_score.refresh_from_db()
        self.assertEqual(self.expert.user_score.total_points, 32)

        self.chunk.refresh_from_db()
        self.assertEqual(self.chunk.status, "resolved")

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, TaskAssignmentStatusChoices.SUBMITTED)

        self.assertEqual(ExpertReview.objects.filter(chunk=self.chunk, expert=self.expert).count(), 1)
