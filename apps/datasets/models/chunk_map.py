from django.db import models

from apps.common.models.base import TimeStampedModel


class DatasetChunk(TimeStampedModel):
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.CASCADE,
        related_name="dataset_chunks",
    )
    chunk = models.ForeignKey(
        "processing.Chunk",
        on_delete=models.CASCADE,
        related_name="dataset_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dataset", "chunk"], name="uniq_datasetchunk_dataset_chunk"),
        ]
        indexes = [
            models.Index(fields=["dataset"]),
            models.Index(fields=["chunk"]),
        ]

    def __str__(self):
        return f"DatasetChunk<{self.dataset_id}:{self.chunk_id}>"