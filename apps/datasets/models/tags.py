from django.db import models

from apps.common.models.base import TimeStampedModel


class DatasetTag(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class DatasetTagMapping(TimeStampedModel):
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.CASCADE,
        related_name="tag_mappings",
    )
    tag = models.ForeignKey(
        DatasetTag,
        on_delete=models.CASCADE,
        related_name="dataset_mappings",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dataset", "tag"], name="uniq_datasettagmapping_dataset_tag"),
        ]
        indexes = [
            models.Index(fields=["dataset"]),
            models.Index(fields=["tag"]),
        ]

    def __str__(self):
        return f"DatasetTagMapping<{self.dataset_id}:{self.tag_id}>"