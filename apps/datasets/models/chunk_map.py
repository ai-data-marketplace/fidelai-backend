from django.db import models

from apps.common.models.base import TimeStampedModel


class DatasetChunk(TimeStampedModel):
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.CASCADE,
        related_name="dataset_chunks",
    )
    nlp_chunk = models.ForeignKey(
        "nlp.NLPChunk",
        on_delete=models.CASCADE,
        related_name="dataset_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dataset", "nlp_chunk"], name="uniq_datasetchunk_dataset_nlpchunk"),
        ]
        indexes = [
            models.Index(fields=["dataset"]),
            models.Index(fields=["nlp_chunk"]),
        ]

    def __str__(self):
        return f"DatasetChunk<{self.dataset_id}:{self.nlp_chunk_id}>"