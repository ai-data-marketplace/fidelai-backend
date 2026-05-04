from __future__ import annotations

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.processing.models import ExpertTaskAssignment, ExpertTaskChunk, ExpertReview, Chunk
from apps.processing.models.chunk import ChunkStatusChoices, TaskAssignmentStatusChoices
from apps.processing.models import Annotation
from apps.scoring.services import score_conflict_resolved, score_expert_review


class ExpertReviewService:
    ACTIVE_ASSIGNMENT_STATUSES = (
        TaskAssignmentStatusChoices.ACCEPTED,
        TaskAssignmentStatusChoices.IN_PROGRESS,
    )

    def get_my_assignments_queryset(self, user):
        return (
            ExpertTaskAssignment.objects.select_related("expert_task")
            .filter(expert=user)
            .annotate(total_chunks=Count("expert_task__task_chunks"))
            .order_by("-assigned_at")
        )

    def get_assignment_for_user(self, assignment_id, user):
        assignment = (
            ExpertTaskAssignment.objects.select_related("expert_task")
            .filter(pk=assignment_id, expert=user)
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
            .select_related("chunk__extracted_document__raw_document", "chunk__consensus")
            .order_by("chunk__order_index")
        )

        chunk_ids = [tc.chunk_id for tc in task_chunks]
        annotation_counts = {
            r["chunk_id"]: r["count"] for r in Annotation.objects.filter(chunk_id__in=chunk_ids).values("chunk_id").annotate(count=Count("id"))
        }

        payload = [
            {
                "chunk": tc.chunk,
                "annotation_count": annotation_counts.get(tc.chunk_id, 0),
            }
            for tc in task_chunks
        ]

        return {"task": task, "chunks": payload}

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
            if ExpertReview.objects.filter(chunk=chunk, expert=user).exists():
                raise ValidationError({"detail": "Duplicate review"})

            expert_review = ExpertReview.objects.create(
                chunk=chunk,
                expert=user,
                domain_match=validated_data.get("domain_match"),
                is_amharic=validated_data.get("is_amharic", False),
                readability=validated_data.get("readability"),
                safety_label=validated_data.get("safety_label"),
                confidence=validated_data.get("confidence"),
                notes=validated_data.get("notes", ""),
                resolution_reasoning=validated_data.get("resolution_reasoning", ""),
            )
            score_expert_review(expert_review)

            final = validated_data["final_decision"]
            if final == ChunkStatusChoices.APPROVED:
                chunk.status = ChunkStatusChoices.APPROVED
            elif final == ChunkStatusChoices.REJECTED:
                chunk.status = ChunkStatusChoices.REJECTED
            else:
                chunk.status = ChunkStatusChoices.RESOLVED
                score_conflict_resolved(expert_review)

            chunk.save(update_fields=["status", "updated_at"])

            # check task completion
            total = ExpertTaskChunk.objects.filter(expert_task=etc.expert_task).count()
            reviewed = ExpertReview.objects.filter(chunk__expert_task_links__expert_task=etc.expert_task).values("chunk_id").distinct().count()
            if reviewed >= total:
                assignment.status = TaskAssignmentStatusChoices.SUBMITTED
                assignment.completed_at = timezone.now()
                assignment.save(update_fields=["status", "completed_at", "updated_at"])

        return {"detail": "Resolved"}
