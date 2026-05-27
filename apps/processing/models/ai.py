from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models.base import TimeStampedModel


class AIQualityCheck(TimeStampedModel):
    chunk = models.OneToOneField(
        "processing.Chunk",
        on_delete=models.CASCADE,
        related_name="ai_quality_check",
    )

    # =========================
    # MODEL 1: XLM-R QC MODEL
    # =========================

    predicted_language = models.CharField(max_length=50)
    language_confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    predicted_domain = models.CharField(max_length=50)
    domain_confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    predicted_readability = models.CharField(max_length=20)
    readability_confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    # =========================
    # MODEL 2: SAFETY MODEL
    # =========================

    predicted_safety = models.CharField(max_length=20)
    safety_confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    # =========================
    # RAW OUTPUTS
    # =========================

    raw_qc_output = models.JSONField(default=dict)
    raw_safety_output = models.JSONField(default=dict)

    # =========================
    # METADATA
    # =========================

    model_name = models.CharField(max_length=255)
    model_version = models.CharField(max_length=100)

    processed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-processed_at",)
        indexes = [
            models.Index(fields=["chunk"]),
            models.Index(fields=["processed_at"]),
        ]

    def __str__(self):
        return f"AIQC<{self.chunk_id}>"
