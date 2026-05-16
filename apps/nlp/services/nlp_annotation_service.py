"""NLP annotation workflow service.

Keeps annotation submission and task/assignment read helpers out of the views.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, Optional

from django.db import transaction
from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from apps.nlp.models import (
    NLPAnnotation,
    NLPAnnotationTask,
    NLPChunk,
    NLPTaskAssignment,
    NLPTaskChunk,
)
from apps.nlp.models.choices import NLPChunkStatusChoices, NLPTaskAssignmentStatusChoices


logger = logging.getLogger(__name__)


class NLPAnnotationConflict(APIException):
    status_code = 409
    default_detail = "You have already annotated this chunk."
    default_code = "conflict"


class NLPAnnotationService:
    MIN_CONSENSUS_ANNOTATIONS = 3

    ACTIVE_ASSIGNMENT_STATUSES = (
        NLPTaskAssignmentStatusChoices.ASSIGNED,
        NLPTaskAssignmentStatusChoices.ACCEPTED,
        NLPTaskAssignmentStatusChoices.IN_PROGRESS,
    )

    TASK_ACCESS_STATUSES = (
        NLPTaskAssignmentStatusChoices.ASSIGNED,
        NLPTaskAssignmentStatusChoices.ACCEPTED,
        NLPTaskAssignmentStatusChoices.IN_PROGRESS,
    )

    def get_assigned_tasks_queryset(self, user, status_filter: Optional[str] = None):
        status_value = status_filter or NLPTaskAssignmentStatusChoices.ASSIGNED
        allowed_statuses = (
            NLPTaskAssignmentStatusChoices.ACCEPTED,
            NLPTaskAssignmentStatusChoices.IN_PROGRESS,
        ) if status_value == "in_progress" else (status_value,)

        return (
            NLPTaskAssignment.objects.select_related("task")
            .filter(annotator=user, status__in=allowed_statuses)
            .order_by("-assigned_at")
        )

    def get_assignment_for_user(self, task_id, user, statuses: Optional[Iterable[str]] = None):
        queryset = NLPTaskAssignment.objects.select_related("task").filter(task_id=task_id, annotator=user)
        if statuses is not None:
            queryset = queryset.filter(status__in=list(statuses))

        try:
            return queryset.get()
        except NLPTaskAssignment.DoesNotExist as exc:
            raise NotFound("Task assignment not found.") from exc

    def get_task_detail_assignment(self, task_id, user):
        annotation_qs = NLPAnnotation.objects.filter(annotator=user).order_by("-created_at")
        task_chunks_qs = (
            NLPTaskChunk.objects.select_related("nlp_chunk")
            .prefetch_related(
                Prefetch("nlp_chunk__annotations", queryset=annotation_qs, to_attr="user_annotations")
            )
            .order_by("order_index")
        )

        queryset = (
            NLPTaskAssignment.objects.select_related("task")
            .prefetch_related(Prefetch("task__task_chunks", queryset=task_chunks_qs, to_attr="prefetched_task_chunks"))
            .filter(annotator=user, task_id=task_id, status__in=self.TASK_ACCESS_STATUSES)
        )

        try:
            return queryset.get()
        except NLPTaskAssignment.DoesNotExist as exc:
            raise NotFound("Task assignment not found.") from exc

    def get_progress(self, assignment: NLPTaskAssignment) -> Dict[str, int]:
        total_chunks = assignment.task.total_chunks or assignment.task.task_chunks.count()
        annotated_chunks = (
            NLPAnnotation.objects.filter(
                annotator=assignment.annotator,
                nlp_chunk__task_assignments__task=assignment.task,
            )
            .values("nlp_chunk_id")
            .distinct()
            .count()
        )
        remaining_chunks = max(total_chunks - annotated_chunks, 0)
        completion_percentage = int((annotated_chunks / total_chunks) * 100) if total_chunks else 0

        return {
            "task_id": assignment.task_id,
            "total_chunks": total_chunks,
            "annotated_chunks": annotated_chunks,
            "remaining_chunks": remaining_chunks,
            "completion_percentage": completion_percentage,
        }

    @transaction.atomic
    def accept_assignment(self, assignment: NLPTaskAssignment) -> NLPTaskAssignment:
        assignment = NLPTaskAssignment.objects.select_for_update().select_related("task").get(pk=assignment.pk)

        if assignment.status != NLPTaskAssignmentStatusChoices.ASSIGNED:
            raise ValidationError({"detail": "Task can only be accepted when it is assigned."})

        assignment.status = NLPTaskAssignmentStatusChoices.ACCEPTED
        if assignment.started_at is None:
            assignment.started_at = timezone.now()
        assignment.save(update_fields=["status", "started_at", "updated_at"])
        return assignment

    @transaction.atomic
    def decline_assignment(self, assignment: NLPTaskAssignment) -> NLPTaskAssignment:
        assignment = NLPTaskAssignment.objects.select_for_update().select_related("task").get(pk=assignment.pk)

        if assignment.status not in (
            NLPTaskAssignmentStatusChoices.ASSIGNED,
            NLPTaskAssignmentStatusChoices.ACCEPTED,
        ):
            raise ValidationError({"detail": "Task can only be declined when it is assigned or accepted."})

        assignment.status = NLPTaskAssignmentStatusChoices.DECLINED
        assignment.save(update_fields=["status", "updated_at"])
        return assignment

    @transaction.atomic
    def submit_annotation(self, user, chunk: NLPChunk, validated_data: Dict[str, object]) -> NLPAnnotation:
        task_chunk = (
            NLPTaskChunk.objects.select_related("task")
            .filter(nlp_chunk=chunk)
            .order_by("order_index")
            .first()
        )
        if task_chunk is None:
            raise NotFound("Chunk not found in any NLP task.")

        assignment = (
            NLPTaskAssignment.objects.select_for_update()
            .select_related("task")
            .filter(
                task=task_chunk.task,
                annotator=user,
                status__in=(
                    NLPTaskAssignmentStatusChoices.ACCEPTED,
                    NLPTaskAssignmentStatusChoices.IN_PROGRESS,
                ),
            )
            .first()
        )

        if assignment is None:
            raise PermissionDenied("You do not have an accepted assignment for this chunk.")

        # Allow annotators to update their existing annotation instead of causing a conflict.
        defaults = {
            "task_assignment": assignment,
            "task_type": task_chunk.task.task_type,
            "labels": validated_data.get("labels"),
            "notes": validated_data.get("notes", ""),
            "confidence_score": validated_data.get("confidence_score"),
            "time_spent_seconds": validated_data.get("time_spent_seconds"),
        }

        annotation, created = NLPAnnotation.objects.update_or_create(
            nlp_chunk=chunk,
            annotator=user,
            defaults=defaults,
        )

        if chunk.status != NLPChunkStatusChoices.IN_ANNOTATION:
            chunk.status = NLPChunkStatusChoices.IN_ANNOTATION
            chunk.save(update_fields=["status", "updated_at"])

        self._maybe_mark_chunk_consensus_ready(chunk=chunk, task=task_chunk.task)

        # Auto-complete assignment if all chunks are annotated
        self._auto_complete_assignment(assignment)

        if created:
            logger.info("Created NLP annotation id=%s for chunk=%s by user=%s", annotation.pk, chunk.pk, user.pk)
        else:
            logger.info("Updated NLP annotation id=%s for chunk=%s by user=%s", annotation.pk, chunk.pk, user.pk)
        return annotation

    def _auto_complete_assignment(self, assignment: NLPTaskAssignment) -> None:
        """Check if assignment is complete and auto-transition to SUBMITTED."""
        total_chunks = assignment.task.total_chunks or assignment.task.task_chunks.count()
        annotated_chunks = NLPAnnotation.objects.filter(task_assignment=assignment).count()

        if total_chunks and annotated_chunks >= total_chunks:
            assignment.status = NLPTaskAssignmentStatusChoices.SUBMITTED
            assignment.completed_at = timezone.now()
            assignment.save(update_fields=["status", "completed_at", "updated_at"])
            logger.info("Auto-completed NLP assignment id=%s (annotator=%s)", assignment.pk, assignment.annotator_id)

    def _maybe_mark_chunk_consensus_ready(self, chunk: NLPChunk, task: NLPAnnotationTask) -> None:
        """Move a chunk to consensus-ready when all participating assignees have annotated it.

        Participating assignees exclude declined assignments. We require all such
        assignees to have submitted one annotation for this chunk and enforce a
        minimum annotation threshold for consensus computation.
        """
        participating_annotator_ids = set(
            NLPTaskAssignment.objects.filter(
                task=task,
                status__in=(
                    NLPTaskAssignmentStatusChoices.ASSIGNED,
                    NLPTaskAssignmentStatusChoices.ACCEPTED,
                    NLPTaskAssignmentStatusChoices.IN_PROGRESS,
                    NLPTaskAssignmentStatusChoices.SUBMITTED,
                ),
            ).values_list("annotator_id", flat=True)
        )

        if not participating_annotator_ids:
            return

        annotated_annotator_ids = set(
            NLPAnnotation.objects.filter(
                nlp_chunk=chunk,
                annotator_id__in=participating_annotator_ids,
            )
            .values_list("annotator_id", flat=True)
            .distinct()
        )

        all_participants_annotated = participating_annotator_ids.issubset(annotated_annotator_ids)
        enough_annotations = len(annotated_annotator_ids) >= self.MIN_CONSENSUS_ANNOTATIONS

        if all_participants_annotated and enough_annotations:
            if chunk.status != NLPChunkStatusChoices.CONSENSUS_READY:
                chunk.status = NLPChunkStatusChoices.CONSENSUS_READY
                chunk.save(update_fields=["status", "updated_at"])


__all__ = ["NLPAnnotationService", "NLPAnnotationConflict"]
