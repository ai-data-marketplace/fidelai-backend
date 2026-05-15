from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.processing.models import ExpertTaskAssignment, ExpertTaskChunk, ExpertReview, Chunk
from apps.processing.models.chunk import ChunkStatusChoices, TaskAssignmentStatusChoices
from apps.processing.models import Annotation
from apps.notifications.services import notify_task_reviewed
from apps.scoring.services import score_conflict_resolved, score_expert_review


logger = logging.getLogger(__name__)


class ExpertReviewService:
    ACTIVE_ASSIGNMENT_STATUSES = (
        TaskAssignmentStatusChoices.ACCEPTED,
        TaskAssignmentStatusChoices.IN_PROGRESS,
    )

    def get_my_assignments_queryset(self, user, status: str | None = None):
        queryset = (
            ExpertTaskAssignment.objects.select_related("expert_task")
            .filter(expert=user)
            .annotate(total_chunks=Count("expert_task__task_chunks"))
            .order_by("-assigned_at")
        )

        if status:
            if status == TaskAssignmentStatusChoices.IN_PROGRESS:
                queryset = queryset.filter(
                    Q(status=TaskAssignmentStatusChoices.ACCEPTED) |
                    Q(status=TaskAssignmentStatusChoices.IN_PROGRESS)
                )
            else:
                queryset = queryset.filter(status=status)
        else:
            queryset = queryset.filter(status=TaskAssignmentStatusChoices.ASSIGNED)

        return queryset

    def get_assignment_for_user(self, expert_task_id, user):
        assignment = (
            ExpertTaskAssignment.objects.select_related("expert_task")
            .filter(expert_task_id=expert_task_id, expert=user)
            .first()
        )
        if not assignment:
            raise PermissionDenied("You do not have permission to access this assignment.")
        return assignment

    def accept_assignment(self, assignment: ExpertTaskAssignment):
        with transaction.atomic():
            assignment = (
                ExpertTaskAssignment.objects.select_for_update()
                .select_related("expert_task")
                .get(pk=assignment.pk)
            )
            if assignment.status != TaskAssignmentStatusChoices.ASSIGNED:
                raise ValidationError({"detail": "Assignment must be in ASSIGNED state."})

            assignment.status = TaskAssignmentStatusChoices.ACCEPTED
            assignment.started_at = timezone.now()
            assignment.save(update_fields=["status", "started_at", "updated_at"])
        return assignment

    def decline_assignment(self, assignment: ExpertTaskAssignment):
        with transaction.atomic():
            assignment = ExpertTaskAssignment.objects.select_for_update().get(pk=assignment.pk)
            if assignment.status != TaskAssignmentStatusChoices.ASSIGNED:
                raise ValidationError({"detail": "Assignment must be in ASSIGNED state."})
            assignment.status = TaskAssignmentStatusChoices.DECLINED
            assignment.save(update_fields=["status", "updated_at"])
        return assignment

    def get_task_chunks(self, assignment: ExpertTaskAssignment):
        if assignment.status not in self.ACTIVE_ASSIGNMENT_STATUSES:
            raise ValidationError({"detail": "Assignment must be accepted or in-progress to view task chunks."})

        task = assignment.expert_task
        task_chunks = (
            ExpertTaskChunk.objects.filter(expert_task=task)
            .exclude(chunk__status__in=(ChunkStatusChoices.APPROVED, ChunkStatusChoices.REJECTED, ChunkStatusChoices.RESOLVED))
            .exclude(chunk__expert_reviews__expert=assignment.expert)
            .select_related("chunk__extracted_document__raw_document", "chunk__consensus")
            .order_by("chunk__order_index")
            .distinct()
        )

        chunk_ids = [tc.chunk_id for tc in task_chunks]
        annotation_counts = {
            r["chunk_id"]: r["count"] for r in Annotation.objects.filter(chunk_id__in=chunk_ids).values("chunk_id").annotate(count=Count("id"))
        }

        payload = [
            {
                "chunk": tc.chunk,
                "annotation_count": annotation_counts.get(tc.chunk_id, 0),
                "domain": task.domain,
            }
            for tc in task_chunks
        ]

        return {"task": task, "chunks": payload}

    def calculate_assignment_progress(self, assignment: ExpertTaskAssignment):
        total_chunks = assignment.expert_task.total_chunks or assignment.expert_task.task_chunks.count()
        reviewed_chunks = (
            ExpertReview.objects.filter(
                expert=assignment.expert,
                chunk__expert_task_links__expert_task=assignment.expert_task,
            )
            .values("chunk_id")
            .distinct()
            .count()
        )
        remaining_chunks = max(total_chunks - reviewed_chunks, 0)
        progress_percentage = int((reviewed_chunks / total_chunks) * 100) if total_chunks else 0

        return {
            "assignment_id": assignment.id,
            "total_chunks": total_chunks,
            "reviewed_chunks": reviewed_chunks,
            "remaining_chunks": remaining_chunks,
            "progress_percentage": progress_percentage,
            "assignment_status": assignment.status,
        }

    def resolve_chunk(self, chunk_id, user, validated_data: dict):
        with transaction.atomic():
            try:
                etc = (
                    ExpertTaskChunk.objects.select_related("expert_task", "chunk")
                    .select_for_update()
                    .get(chunk_id=chunk_id)
                )
            except ExpertTaskChunk.DoesNotExist:
                raise ValidationError({"detail": "Chunk not part of any expert task"})

            assignment = (
                ExpertTaskAssignment.objects.select_for_update()
                .filter(expert_task=etc.expert_task, expert=user, status__in=self.ACTIVE_ASSIGNMENT_STATUSES)
                .first()
            )
            if not assignment:
                raise PermissionDenied("Forbidden or no active assignment")

            chunk = etc.chunk
            expert_review, _ = ExpertReview.objects.update_or_create(
                chunk=chunk,
                expert=user,
                defaults={
                    "domain_match": validated_data.get("domain_match"),
                    "is_amharic": validated_data.get("is_amharic", False),
                    "readability": validated_data.get("readability"),
                    "safety_label": validated_data.get("safety_label"),
                    "confidence": validated_data.get("confidence"),
                    "notes": validated_data.get("notes", ""),
                    "resolution_reasoning": validated_data.get("resolution_reasoning", ""),
                },
            )
            score_expert_review(expert_review)

            if assignment.status == TaskAssignmentStatusChoices.ACCEPTED:
                assignment.status = TaskAssignmentStatusChoices.IN_PROGRESS
                assignment.save(update_fields=["status", "updated_at"])

            final = validated_data["final_decision"]
            if final == ChunkStatusChoices.APPROVED:
                chunk.status = ChunkStatusChoices.APPROVED
            elif final == ChunkStatusChoices.REJECTED:
                chunk.status = ChunkStatusChoices.REJECTED
            else:
                chunk.status = ChunkStatusChoices.RESOLVED
                score_conflict_resolved(expert_review)

            chunk.save(update_fields=["status", "updated_at"])

            try:
                notify_task_reviewed(user=user, chunk_id=chunk.id)
            except ValueError:
                logger.warning("Notification template missing for expert review chunk=%s expert=%s", chunk.id, user.id)

            # check task completion
            total = ExpertTaskChunk.objects.filter(expert_task=etc.expert_task).count()
            reviewed = ExpertReview.objects.filter(chunk__expert_task_links__expert_task=etc.expert_task).values("chunk_id").distinct().count()
            if reviewed >= total:
                assignment.status = TaskAssignmentStatusChoices.SUBMITTED
                assignment.completed_at = timezone.now()
                assignment.save(update_fields=["status", "completed_at", "updated_at"])

        return {"detail": "Resolved"}
