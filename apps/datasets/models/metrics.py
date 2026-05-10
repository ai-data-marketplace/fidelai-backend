from django.db import models

from apps.common.models.base import TimeStampedModel


class DatasetMetrics(TimeStampedModel):
    dataset = models.OneToOneField(
        "datasets.Dataset",
        on_delete=models.CASCADE,
        related_name="metrics",
    )
    total_documents = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    token_count = models.PositiveBigIntegerField(default=0)
    label_distribution = models.JSONField(default=dict)
    domain_distribution = models.JSONField(default=dict)
    avg_qc_score = models.FloatField()
    annotation_coverage = models.FloatField()
    expert_validation_ratio = models.FloatField()
    dataset_size_bytes = models.PositiveBigIntegerField(default=0)
    computed_at = models.DateTimeField()

    class Meta:
        ordering = ("-computed_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(avg_qc_score__gte=0.0) & models.Q(avg_qc_score__lte=1.0),
                name="chk_datasetmetrics_avg_qc_score_range",
            ),
            models.CheckConstraint(
                condition=models.Q(annotation_coverage__gte=0.0) & models.Q(annotation_coverage__lte=1.0),
                name="chk_datasetmetrics_annotation_coverage_range",
            ),
            models.CheckConstraint(
                condition=models.Q(expert_validation_ratio__gte=0.0)
                & models.Q(expert_validation_ratio__lte=1.0),
                name="chk_datasetmetrics_expert_validation_ratio_range",
            ),
        ]
        indexes = [
            models.Index(fields=["computed_at"]),
        ]

    def __str__(self):
        return f"DatasetMetrics<{self.dataset_id}:{self.computed_at}>"