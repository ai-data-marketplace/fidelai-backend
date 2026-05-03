from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.processing.models.chunk import (
    Chunk,
    DomainMatchChoices,
    ReadabilityChoices,
    SafetyChoices,
)


class Consensus(TimeStampedModel):
    chunk = models.OneToOneField(
        Chunk,
        on_delete=models.CASCADE,
        related_name="consensus",
    )

    final_domain_match = models.CharField(
        max_length=20,
        choices=DomainMatchChoices.choices,
    )

    final_is_amharic = models.BooleanField()
    
    final_readability = models.CharField(
        max_length=10,
        choices=ReadabilityChoices.choices,
    )

    final_safety_label = models.CharField(
        max_length=10,
        choices=SafetyChoices.choices,
    )

    agreement_score = models.FloatField()

    requires_expert_review = models.BooleanField(default=False)

    total_annotations = models.PositiveIntegerField(default=0)

    computed_at = models.DateTimeField()

    class Meta:
        ordering = ("-computed_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(agreement_score__gte=0.0) &
                          models.Q(agreement_score__lte=1.0),
                name="chk_consensus_agreement_score_range",
            ),
        ]
        indexes = [
            models.Index(fields=["requires_expert_review"]),
            models.Index(fields=["computed_at"]),
        ]

    def __str__(self):
        return f"Consensus<{self.chunk_id}:{self.agreement_score}>"
