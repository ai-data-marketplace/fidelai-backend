from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.documents.models import RawDocument
from apps.processing.models import Chunk, ExtractedDocument
from apps.scoring.models import ScoreActionTypeChoices, ScoreConfig, ScoreLog, UserScore
from apps.scoring.services import (
    award_points,
    score_annotation_consensus,
    score_annotation_submitted,
    score_conflict_resolved,
    score_expert_review,
)
from apps.users.models import CustomUser, RoleChoices


class ScoringServiceTests(TestCase):
    def setUp(self):
        self.annotator = CustomUser.objects.create_user(
            email="annotator@example.com",
            username="annotator",
            full_name="Annotator User",
            password="password123",
            role=RoleChoices.ANNOTATOR,
            is_verified=True,
        )
        self.expert = CustomUser.objects.create_user(
            email="expert@example.com",
            username="expert",
            full_name="Expert User",
            password="password123",
            role=RoleChoices.EXPERT,
            is_verified=True,
        )
        self.chunk = self._create_chunk()

        self.score_values = {
            ScoreActionTypeChoices.ANNOTATION_SUBMITTED: 5,
            ScoreActionTypeChoices.ANNOTATION_MATCH_CONSENSUS: 8,
            ScoreActionTypeChoices.ANNOTATION_BELOW_THRESHOLD: -2,
            ScoreActionTypeChoices.EXPERT_REVIEW_COMPLETED: 12,
            ScoreActionTypeChoices.CONFLICT_RESOLVED: 20,
        }
        for action_type, points_value in self.score_values.items():
            ScoreConfig.objects.create(action_type=action_type, points_value=points_value)

        UserScore.objects.create(user=self.annotator, total_points=0)
        UserScore.objects.create(user=self.expert, total_points=0)

    def _create_chunk(self):
        raw_document = RawDocument.objects.create(
            user=self.annotator,
            title="Score Document",
            description="Score fixture",
            domain="other",
            language="amharic",
            consent_given=True,
        )
        extracted_document = ExtractedDocument.objects.create(
            raw_document=raw_document,
            full_text="sample chunk",
            structure=[],
            layout_metadata={},
            language_detected="amharic",
            confidence_score=1,
            processed_at=timezone.now(),
        )
        return Chunk.objects.create(
            extracted_document=extracted_document,
            text="sample chunk",
            order_index=0,
            char_start=0,
            char_end=12,
            token_count=2,
            metadata={"fixture": True},
        )

    def test_annotation_submission_adds_score(self):
        annotation = SimpleNamespace(id=1, annotator=self.annotator, chunk=self.chunk)

        score_log = score_annotation_submitted(annotation)

        self.assertIsNotNone(score_log)
        self.assertEqual(ScoreLog.objects.count(), 1)
        self.annotator.user_score.refresh_from_db()
        self.assertEqual(self.annotator.user_score.total_points, 5)

    def test_duplicate_submission_does_not_double_score(self):
        annotation = SimpleNamespace(id=1, annotator=self.annotator, chunk=self.chunk)

        first_log = award_points(
            user=self.annotator,
            role=RoleChoices.ANNOTATOR,
            action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED,
            chunk=self.chunk,
        )
        second_log = award_points(
            user=self.annotator,
            role=RoleChoices.ANNOTATOR,
            action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED,
            chunk=self.chunk,
        )

        self.assertIsNotNone(first_log)
        self.assertIsNone(second_log)
        self.assertEqual(ScoreLog.objects.count(), 1)
        self.annotator.user_score.refresh_from_db()
        self.assertEqual(self.annotator.user_score.total_points, 5)

    def test_consensus_scoring_works_correctly(self):
        annotation = SimpleNamespace(id=2, annotator=self.annotator, chunk=self.chunk)

        score_log = score_annotation_consensus(annotation, matches=True)

        self.assertIsNotNone(score_log)
        self.assertEqual(score_log.action_type, ScoreActionTypeChoices.ANNOTATION_MATCH_CONSENSUS)
        self.annotator.user_score.refresh_from_db()
        self.assertEqual(self.annotator.user_score.total_points, 8)

    def test_negative_scoring_below_threshold_works(self):
        annotation = SimpleNamespace(id=3, annotator=self.annotator, chunk=self.chunk)

        score_log = score_annotation_consensus(annotation, matches=False)

        self.assertIsNotNone(score_log)
        self.assertEqual(score_log.action_type, ScoreActionTypeChoices.ANNOTATION_BELOW_THRESHOLD)
        self.annotator.user_score.refresh_from_db()
        self.assertEqual(self.annotator.user_score.total_points, -2)

    def test_expert_review_adds_score(self):
        expert_review = SimpleNamespace(id=4, expert=self.expert, chunk=self.chunk)

        score_log = score_expert_review(expert_review)

        self.assertIsNotNone(score_log)
        self.assertEqual(score_log.action_type, ScoreActionTypeChoices.EXPERT_REVIEW_COMPLETED)
        self.expert.user_score.refresh_from_db()
        self.assertEqual(self.expert.user_score.total_points, 12)

    def test_conflict_resolved_adds_score(self):
        expert_review = SimpleNamespace(id=5, expert=self.expert, chunk=self.chunk)

        score_log = score_conflict_resolved(expert_review)

        self.assertIsNotNone(score_log)
        self.assertEqual(score_log.action_type, ScoreActionTypeChoices.CONFLICT_RESOLVED)
        self.expert.user_score.refresh_from_db()
        self.assertEqual(self.expert.user_score.total_points, 20)

    def test_invalid_role_action_rejected(self):
        with self.assertRaisesMessage(ValueError, "Invalid scoring configuration"):
            award_points(
                user=self.annotator,
                role=RoleChoices.BUYER,
                action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED,
                chunk=self.chunk,
            )

        with self.assertRaisesMessage(ValueError, "Invalid action_type for role"):
            award_points(
                user=self.annotator,
                role=RoleChoices.ANNOTATOR,
                action_type=ScoreActionTypeChoices.EXPERT_REVIEW_COMPLETED,
                chunk=self.chunk,
            )

    def test_missing_score_config_raises(self):
        ScoreConfig.objects.filter(action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED).delete()

        with self.assertRaisesMessage(ValueError, "ScoreConfig not defined for action"):
            award_points(
                user=self.annotator,
                role=RoleChoices.ANNOTATOR,
                action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED,
                chunk=self.chunk,
            )

    def test_transaction_rollback_works(self):
        with patch("apps.scoring.models.user_score.UserScore.save", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                award_points(
                    user=self.annotator,
                    role=RoleChoices.ANNOTATOR,
                    action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED,
                    chunk=self.chunk,
                )

        self.assertEqual(ScoreLog.objects.count(), 0)
        self.annotator.user_score.refresh_from_db()
        self.assertEqual(self.annotator.user_score.total_points, 0)