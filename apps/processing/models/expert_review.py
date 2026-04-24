from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.documents.models import DomainChoices
from apps.processing.models.chunk import (
    Chunk,
    ConfidenceChoices,
    DomainMatchChoices,
    ReadabilityChoices,
    SafetyChoices,
)


class ExpertTask(TimeStampedModel):
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=20, choices=DomainChoices.choices)

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
