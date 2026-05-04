from __future__ import annotations

from django.db import transaction

from apps.scoring.models import ScoreActionTypeChoices, ScoreConfig, ScoreLog, UserScore
from apps.users.models.roles import RoleChoices


ANNOTATOR_ACTIONS = (
    ScoreActionTypeChoices.ANNOTATION_SUBMITTED,
    ScoreActionTypeChoices.ANNOTATION_MATCH_CONSENSUS,
    ScoreActionTypeChoices.ANNOTATION_BELOW_THRESHOLD,
)

EXPERT_ACTIONS = (
    ScoreActionTypeChoices.EXPERT_REVIEW_COMPLETED,
    ScoreActionTypeChoices.CONFLICT_RESOLVED,
)

ROLE_ACTIONS = {
    RoleChoices.ANNOTATOR: ANNOTATOR_ACTIONS,
    RoleChoices.EXPERT: EXPERT_ACTIONS,
}


def _validate_role_action(role, action_type):
    if role not in ROLE_ACTIONS:
        raise ValueError("Invalid scoring configuration")
    if action_type not in ROLE_ACTIONS[role]:
        raise ValueError("Invalid action_type for role")


def _resolve_points(action_type):
    try:
        return ScoreConfig.objects.get(action_type=action_type).points_value
    except ScoreConfig.DoesNotExist as exc:
        raise ValueError("ScoreConfig not defined for action") from exc


def award_points(*, user, role, action_type, chunk=None, document=None, dataset=None, metadata=None):
    _validate_role_action(role, action_type)
    points = _resolve_points(action_type)

    with transaction.atomic():
        user_score, _ = UserScore.objects.select_for_update().get_or_create(user=user)

        if ScoreLog.objects.filter(user=user, action_type=action_type, chunk=chunk).exists():
            return None

        score_log = ScoreLog.objects.create(
            user=user,
            role=role,
            action_type=action_type,
            points=points,
            chunk=chunk,
            document=document,
            dataset=dataset,
            metadata=metadata or {},
        )

        user_score.total_points += points
        user_score.save(update_fields=["total_points", "updated_at"])

    return score_log


def score_annotation_submitted(annotation):
    return award_points(
        user=annotation.annotator,
        role=RoleChoices.ANNOTATOR,
        action_type=ScoreActionTypeChoices.ANNOTATION_SUBMITTED,
        chunk=annotation.chunk,
        metadata={"annotation_id": str(annotation.id)},
    )


def score_annotation_consensus(annotation, matches: bool):
    action_type = (
        ScoreActionTypeChoices.ANNOTATION_MATCH_CONSENSUS
        if matches
        else ScoreActionTypeChoices.ANNOTATION_BELOW_THRESHOLD
    )
    return award_points(
        user=annotation.annotator,
        role=RoleChoices.ANNOTATOR,
        action_type=action_type,
        chunk=annotation.chunk,
        metadata={"annotation_id": str(annotation.id), "matches": matches},
    )


def score_expert_review(expert_review):
    return award_points(
        user=expert_review.expert,
        role=RoleChoices.EXPERT,
        action_type=ScoreActionTypeChoices.EXPERT_REVIEW_COMPLETED,
        chunk=expert_review.chunk,
        metadata={"expert_review_id": str(expert_review.id)},
    )


def score_conflict_resolved(expert_review):
    return award_points(
        user=expert_review.expert,
        role=RoleChoices.EXPERT,
        action_type=ScoreActionTypeChoices.CONFLICT_RESOLVED,
        chunk=expert_review.chunk,
        metadata={"expert_review_id": str(expert_review.id)},
    )