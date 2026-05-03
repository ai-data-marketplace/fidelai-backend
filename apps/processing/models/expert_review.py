from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.documents.models import DomainChoices
from apps.processing.models.chunk import (
    Chunk,
    ConfidenceChoices,
    DomainMatchChoices,
    ReadabilityChoices,
    TaskAssignmentStatusChoices,
    SafetyChoices,
)


class ExpertTask(TimeStampedModel):
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=20, choices=DomainChoices.choices)
    total_chunks = models.PositiveIntegerField(default=0)
    created_from_consensus = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["domain"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"ExpertTask<{self.name}:{self.domain}>"


class ExpertTaskChunk(TimeStampedModel):
    expert_task = models.ForeignKey(
        ExpertTask,
        on_delete=models.CASCADE,
        related_name="task_chunks",
    )
    chunk = models.ForeignKey(
        Chunk,
        on_delete=models.CASCADE,
        related_name="expert_task_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["expert_task", "chunk"],
                name="uniq_experttaskchunk_task_chunk",
            ),
        ]
        indexes = [
            models.Index(fields=["expert_task"]),
            models.Index(fields=["chunk"]),
        ]

    def __str__(self):
        return f"ExpertTaskChunk<{self.expert_task_id}:{self.chunk_id}>"


class ExpertTaskAssignment(TimeStampedModel):
    expert_task = models.ForeignKey(
        ExpertTask,
        on_delete=models.CASCADE,
        related_name="expert_assignments",
    )
    expert = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="expert_task_assignments",
    )
    status = models.CharField(max_length=20, choices=TaskAssignmentStatusChoices.choices, default=TaskAssignmentStatusChoices.ASSIGNED)
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-assigned_at",)
        constraints = [
            models.UniqueConstraint(fields=["expert_task"], name="one_expert_per_task"),
            models.UniqueConstraint(fields=["expert_task", "expert"], name="uniq_experttaskassignment_task_expert"),
        ]
        indexes = [
            models.Index(fields=["expert_task"]),
            models.Index(fields=["expert"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"ExpertTaskAssignment<{self.expert_task_id}:{self.expert_id}:{self.status}>"


class ExpertReview(TimeStampedModel):
    chunk = models.ForeignKey(
        Chunk,
        on_delete=models.CASCADE,
        related_name="expert_reviews",
    )
    expert = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="expert_reviews",
    )

    domain_match = models.CharField(max_length=20, choices=DomainMatchChoices.choices)
    is_amharic = models.BooleanField()
    readability = models.CharField(max_length=10, choices=ReadabilityChoices.choices)
    safety_label = models.CharField(max_length=10, choices=SafetyChoices.choices)
    confidence = models.CharField(max_length=10, choices=ConfidenceChoices.choices)
    notes = models.TextField(blank=True)
    resolution_reasoning = models.TextField()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["chunk", "expert"], name="uniq_expertreview_chunk_expert"),
        ]
        indexes = [
            models.Index(fields=["chunk"]),
            models.Index(fields=["expert"]),
        ]

    def __str__(self):
        return f"ExpertReview<{self.chunk_id}:{self.expert_id}>"
