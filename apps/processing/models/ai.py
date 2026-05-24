from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.processing.models.chunk import (
    Chunk,
    ConfidenceChoices,
    DomainMatchChoices,
    ReadabilityChoices,
    SafetyChoices,
)


from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class AIQualityCheck(TimeStampedModel):
    chunk = models.OneToOneField(
        Chunk,
        on_delete=models.CASCADE,
        related_name="ai_quality_check",
    )

    predicted_language = models.CharField(max_length=50)
    language_confidence = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])

    predicted_domain = models.CharField(max_length=50)
    domain_confidence = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])

    predicted_readability = models.CharField(max_length=20)
    readability_confidence = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])

    overall_confidence_score = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])

    requires_manual_review = models.BooleanField(default=False)

    model_name = models.CharField(max_length=255)
    model_version = models.CharField(max_length=100)

    raw_predictions = models.JSONField(default=dict)

    processed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-processed_at",)
        indexes = [
            models.Index(fields=["chunk"]),
            models.Index(fields=["processed_at"]),
            models.Index(fields=["requires_manual_review"]),
        ]
       

    def __str__(self):
        return f"AIQualityCheck<Chunk={self.chunk_id}, lang={self.predicted_language}, dom={self.predicted_domain}, read={self.predicted_readability}>"
