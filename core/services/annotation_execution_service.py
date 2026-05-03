from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.processing.models import Annotation, Chunk, ChunkStatusChoices, TaskAssignment, TaskAssignmentStatusChoices, TaskChunk


class AnnotationExecutionService:
    ACTIVE_ASSIGNMENT_STATUSES = (
        TaskAssignmentStatusChoices.ACCEPTED,
        TaskAssignmentStatusChoices.IN_PROGRESS,
    )
    CONSENSUS_ANNOTATIONS_PER_CHUNK = 3

    def get_my_assignments_queryset(self, user, status: str | None = None):
        queryset = (
            TaskAssignment.objects.select_related("task")
            .filter(annotator=user)
            .annotate(
                total_chunks=Coalesce(F("task__total_chunks"), Count("task__task_chunks", distinct=True)),
                annotated_chunks=Count("annotations", distinct=True),
                completed_annotations=Count(
                    "annotations",
                    filter=Q(annotations__is_skipped=False),
                    distinct=True,
                ),
                skipped_annotations=Count(
                    "annotations",
                    filter=Q(annotations__is_skipped=True),
                    distinct=True,
                ),
            )
            .order_by("-assigned_at")
        )

        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_assignment_for_user(self, assignment_id, user):
        assignment = (
            TaskAssignment.objects.select_related("task", "annotator")
            .filter(pk=assignment_id, annotator=user)
            .first()
        )
        if not assignment:
            raise PermissionDenied("You do not have permission to access this assignment.")
        return assignment

    def accept_task_assignment(self, assignment: TaskAssignment):
        with transaction.atomic():
            assignment = TaskAssignment.objects.select_for_update().select_related("task", "annotator").get(pk=assignment.pk)
            if assignment.status != TaskAssignmentStatusChoices.ASSIGNED:
                raise ValidationError({"detail": "Task assignment must be in ASSIGNED state."})

            assignment.status = TaskAssignmentStatusChoices.ACCEPTED
            assignment.started_at = timezone.now()
            assignment.save(update_fields=["status", "started_at", "updated_at"])
        return assignment

    def decline_task_assignment(self, assignment: TaskAssignment):
        with transaction.atomic():
            assignment = TaskAssignment.objects.select_for_update().get(pk=assignment.pk)
            if assignment.status != TaskAssignmentStatusChoices.ASSIGNED:
                raise ValidationError({"detail": "Task assignment must be in ASSIGNED state."})

            assignment.status = TaskAssignmentStatusChoices.DECLINED
            assignment.save(update_fields=["status", "updated_at"])
        return assignment

    def get_assignment_chunks_queryset(self, assignment: TaskAssignment):
        if assignment.status not in self.ACTIVE_ASSIGNMENT_STATUSES:
            raise ValidationError({"detail": "Task must be accepted before annotation."})

        annotation_id_subquery = Annotation.objects.filter(
            chunk=OuterRef("chunk_id"),
            annotator=assignment.annotator,
        ).values("id")[:1]

        return (
            TaskChunk.objects.filter(task=assignment.task)
            .select_related("chunk")
            .annotate(
                annotation_exists=Exists(
                    Annotation.objects.filter(
                        chunk=OuterRef("chunk_id"),
                        annotator=assignment.annotator,
                    )
                ),
                annotation_id=Subquery(annotation_id_subquery),
            )
            .order_by("order_index")
        )

    def submit_chunk_annotation(self, *, assignment: TaskAssignment, chunk: Chunk, annotator, validated_data: dict):
        with transaction.atomic():
            assignment = TaskAssignment.objects.select_for_update().select_related("task", "annotator").get(pk=assignment.pk)

            if assignment.annotator_id != annotator.id:
                raise PermissionDenied("You do not have permission to access this assignment.")

            if assignment.status not in self.ACTIVE_ASSIGNMENT_STATUSES:
                raise ValidationError({"detail": "Task must be accepted before annotation."})

            if not TaskChunk.objects.filter(task=assignment.task, chunk=chunk).exists():
                raise ValidationError({"detail": "Chunk does not belong to this assignment."})

            if Annotation.objects.filter(chunk=chunk, annotator=annotator).exists():
                raise ValidationError({"detail": "You have already annotated this chunk."})

            annotation = Annotation.objects.create(
                chunk=chunk,
                annotator=annotator,
                task_assignment=assignment,
                **validated_data,
            )

            self.update_chunk_status_after_annotation(chunk=chunk, task_id=assignment.task_id)

            if assignment.status == TaskAssignmentStatusChoices.ACCEPTED:
                assignment.status = TaskAssignmentStatusChoices.IN_PROGRESS

            assignment = self.auto_complete_assignment(assignment)

        return annotation, assignment

    def update_chunk_status_after_annotation(self, *, chunk: Chunk, task_id):
        chunk = Chunk.objects.select_for_update().get(pk=chunk.pk)

        annotation_count = (
            Annotation.objects.filter(
                chunk=chunk,
                task_assignment__task_id=task_id,
            )
            .values("annotator_id")
            .distinct()
            .count()
        )

        consensus_target = getattr(
            settings,
            "PROCESSING_CONSENSUS_ANNOTATIONS_PER_CHUNK",
            self.CONSENSUS_ANNOTATIONS_PER_CHUNK,
        )

        if annotation_count >= consensus_target:
            if chunk.status != ChunkStatusChoices.ANNOTATED:
                chunk.status = ChunkStatusChoices.ANNOTATED
                chunk.save(update_fields=["status", "updated_at"])
            return

        if chunk.status != ChunkStatusChoices.IN_ANNOTATION:
            chunk.status = ChunkStatusChoices.IN_ANNOTATION
            chunk.save(update_fields=["status", "updated_at"])

    def calculate_assignment_progress(self, assignment: TaskAssignment):
        total_chunks = assignment.task.total_chunks or assignment.task.task_chunks.count()
        completed_annotations = Annotation.objects.filter(task_assignment=assignment, is_skipped=False).count()
        skipped_annotations = Annotation.objects.filter(task_assignment=assignment, is_skipped=True).count()
        annotated_chunks = completed_annotations + skipped_annotations
        remaining_chunks = max(total_chunks - annotated_chunks, 0)
        progress_percentage = int((annotated_chunks / total_chunks) * 100) if total_chunks else 0

        return {
            "assignment_id": assignment.id,
            "total_chunks": total_chunks,
            "completed_annotations": completed_annotations,
            "skipped_annotations": skipped_annotations,
            "remaining_chunks": remaining_chunks,
            "progress_percentage": progress_percentage,
            "assignment_status": assignment.status,
        }

    def auto_complete_assignment(self, assignment: TaskAssignment):
        total_chunks = assignment.task.total_chunks or assignment.task.task_chunks.count()
        annotated_chunks = Annotation.objects.filter(task_assignment=assignment).count()

        if total_chunks and annotated_chunks >= total_chunks:
            assignment.status = TaskAssignmentStatusChoices.SUBMITTED
            assignment.completed_at = timezone.now()
            assignment.save(update_fields=["status", "completed_at", "updated_at"])
        else:
            assignment.save(update_fields=["status", "updated_at"])

        return assignment