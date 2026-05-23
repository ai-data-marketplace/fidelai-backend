from __future__ import annotations

from django.db import transaction

from apps.scoring.models import ScoreActionTypeChoices, ScoreConfig, ScoreLog, UserScore
from apps.users.models.roles import RoleChoices


ANNOTATOR_ACTIONS = (
    ScoreActionTypeChoices.ANNOTATION_SUBMITTED,
    ScoreActionTypeChoices.ANNOTATION_MATCH_CONSENSUS,
    ScoreActionTypeChoices.ANNOTATION_BELOW_THRESHOLD,
)

CONTRIBUTOR_ACTIONS = (
    ScoreActionTypeChoices.DOCUMENT_APPROVED,
    ScoreActionTypeChoices.DATASET_INCLUDED,
    ScoreActionTypeChoices.DATASET_SOLD,
)

EXPERT_ACTIONS = (
    ScoreActionTypeChoices.EXPERT_REVIEW_COMPLETED,
    ScoreActionTypeChoices.CONFLICT_RESOLVED,
)

ROLE_ACTIONS = {
    RoleChoices.CONTRIBUTOR: CONTRIBUTOR_ACTIONS,
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

        score_log_filter = {
            "user": user,
            "action_type": action_type,
        }
        if chunk is not None:
            score_log_filter["chunk"] = chunk
        elif document is not None:
            score_log_filter["document"] = document
        elif dataset is not None:
            score_log_filter["dataset"] = dataset

        if ScoreLog.objects.filter(**score_log_filter).exists():
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


def score_document_approved(raw_document):
    return award_points(
        user=raw_document.user,
        role=RoleChoices.CONTRIBUTOR,
        action_type=ScoreActionTypeChoices.DOCUMENT_APPROVED,
        document=raw_document,
        metadata={"raw_document_id": str(raw_document.id)},
    )


def contributor_users_for_dataset(dataset):
    from apps.datasets.models.chunk_map import DatasetChunk
    from apps.users.models import CustomUser

    contributor_ids = (
        DatasetChunk.objects.filter(dataset=dataset)
        .exclude(nlp_chunk__source_chunk__extracted_document__raw_document__user_id__isnull=True)
        .values_list(
            "nlp_chunk__source_chunk__extracted_document__raw_document__user_id",
            flat=True,
        )
        .distinct()
    )
    return CustomUser.objects.filter(id__in=contributor_ids)


def _award_dataset_contributors(*, dataset, action_type):
    metadata = {"dataset_id": str(dataset.id)}
    score_logs = []
    for user in contributor_users_for_dataset(dataset):
        score_log = award_points(
            user=user,
            role=RoleChoices.CONTRIBUTOR,
            action_type=action_type,
            dataset=dataset,
            metadata=metadata,
        )
        if score_log is not None:
            score_logs.append(score_log)
    return score_logs


def score_dataset_included(dataset):
    return _award_dataset_contributors(
        dataset=dataset,
        action_type=ScoreActionTypeChoices.DATASET_INCLUDED,
    )


def score_dataset_sold(dataset):
    return _award_dataset_contributors(
        dataset=dataset,
        action_type=ScoreActionTypeChoices.DATASET_SOLD,
    )