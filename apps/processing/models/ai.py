from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.processing.models.chunk import (
    Chunk,
    ConfidenceChoices,
    DomainMatchChoices,
    ReadabilityChoices,
    SafetyChoices,
)


class AIQualityCheck(TimeStampedModel):
    chunk = models.OneToOneField(
        Chunk,
        on_delete=models.CASCADE,
        related_name="ai_quality_check",
    )
    domain_match = models.CharField(max_length=20, choices=DomainMatchChoices.choices)
    is_amharic = models.BooleanField()
    readability = models.CharField(max_length=10, choices=ReadabilityChoices.choices)
    safety_label = models.CharField(max_length=10, choices=SafetyChoices.choices)
    confidence = models.CharField(max_length=10, choices=ConfidenceChoices.choices)
    model_name = models.CharField(max_length=255)
    model_version = models.CharField(max_length=100)
    processed_at = models.DateTimeField()

    class Meta:
        ordering = ("-processed_at",)
        indexes = [
            models.Index(fields=["processed_at"]),
        ]

    def __str__(self):
        return f"AIQualityCheck<{self.chunk_id}:{self.model_name}:{self.model_version}>"
