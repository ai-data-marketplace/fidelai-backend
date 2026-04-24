from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.processing.models.chunk import (
    Chunk,
    ConfidenceChoices,
    DomainMatchChoices,
    ReadabilityChoices,
    SafetyChoices,
)


class Annotation(TimeStampedModel):
    chunk = models.ForeignKey(
        Chunk,
        on_delete=models.CASCADE,
        related_name="annotations",
    )
    annotator = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="annotations",
    )
    task_assignment = models.ForeignKey(
        "processing.TaskAssignment",
        on_delete=models.CASCADE,
        related_name="annotations",
    )

    domain_match = models.CharField(max_length=20, choices=DomainMatchChoices.choices)
    is_amharic = models.BooleanField()
    readability = models.CharField(max_length=10, choices=ReadabilityChoices.choices)
    safety_label = models.CharField(max_length=10, choices=SafetyChoices.choices)
    confidence = models.CharField(max_length=10, choices=ConfidenceChoices.choices)
    notes = models.TextField(blank=True)

    time_spent_seconds = models.PositiveIntegerField(blank=True, null=True)
    is_skipped = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["chunk", "annotator"], name="uniq_annotation_chunk_annotator"),
        ]
        indexes = [
            models.Index(fields=["chunk"]),
            models.Index(fields=["annotator"]),
            models.Index(fields=["task_assignment"]),
            models.Index(fields=["chunk", "annotator"]),
        ]

    def __str__(self):
        return f"Annotation<{self.chunk_id}:{self.annotator_id}>"
