from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.documents.models import DomainChoices
from apps.processing.models.chunk import Chunk, TaskAssignmentStatusChoices


class AnnotationTask(TimeStampedModel):
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=20, choices=DomainChoices.choices)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        related_name="created_annotation_tasks",
        blank=True,
        null=True,
    )
    total_chunks = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["domain"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"AnnotationTask<{self.name}:{self.domain}>"


class TaskChunk(TimeStampedModel):
    task = models.ForeignKey(
        AnnotationTask,
        on_delete=models.CASCADE,
        related_name="task_chunks",
    )
    chunk = models.ForeignKey(
        Chunk,
        on_delete=models.CASCADE,
        related_name="task_links",
    )
    order_index = models.PositiveIntegerField()

    class Meta:
        ordering = ("task", "order_index")
        constraints = [
            models.UniqueConstraint(fields=["task", "chunk"], name="uniq_taskchunk_task_chunk"),
            models.UniqueConstraint(fields=["task", "order_index"], name="uniq_taskchunk_task_order"),
        ]
        indexes = [
            models.Index(fields=["task", "order_index"]),
        ]

    def __str__(self):
        return f"TaskChunk<{self.task_id}:{self.chunk_id}:{self.order_index}>"


class TaskAssignment(TimeStampedModel):
    task = models.ForeignKey(
        AnnotationTask,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    annotator = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="task_assignments",
    )
    status = models.CharField(
        max_length=20,
        choices=TaskAssignmentStatusChoices.choices,
        default=TaskAssignmentStatusChoices.ASSIGNED,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-assigned_at",)
        constraints = [
            models.UniqueConstraint(fields=["task", "annotator"], name="uniq_taskassignment_task_annotator"),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["task"]),
            models.Index(fields=["annotator"]),
            models.Index(fields=["task", "status"]),
            models.Index(fields=["annotator", "status"]),
        ]

    def __str__(self):
        return f"TaskAssignment<{self.task_id}:{self.annotator_id}:{self.status}>"
