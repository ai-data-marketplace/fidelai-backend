from django.db import models

from apps.common.models.base import TimeStampedModel


class DatasetFileFormatChoices(models.TextChoices):
    JSONL = "jsonl", "JSONL"
    CSV = "csv", "CSV"
    TSV = "tsv", "TSV"
    TXT = "txt", "TXT"


class DatasetAsset(TimeStampedModel):
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.CASCADE,
        related_name="assets",
    )
    file = models.FileField(upload_to="datasets/assets/%Y/%m/%d/")
    file_format = models.CharField(max_length=10, choices=DatasetFileFormatChoices.choices)
    file_size_bytes = models.PositiveBigIntegerField()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "file_format"],
                name="uniq_datasetasset_dataset_file_format",
            ),
        ]
        indexes = [
            models.Index(fields=["dataset"]),
            models.Index(fields=["file_format"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"DatasetAsset<{self.dataset_id}:{self.file_format}>"