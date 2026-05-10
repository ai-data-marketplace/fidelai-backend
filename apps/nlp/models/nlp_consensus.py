"""
NLP consensus model - Consensus results from multiple annotations.

Aggregates multiple NLP annotations into final consensus labels.
Supports multiple NLP task types with flexible JSONField output.
"""

from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.nlp.models.choices import NLPTaskTypeChoices


class NLPConsensus(TimeStampedModel):
    """
    Represents the consensus result for annotations of a single NLP chunk.
    
    Similar to QC consensus but for NLP labels.
    Aggregates multiple annotations into final consensus output.
    
    CRITICAL DESIGN: Supports MULTIPLE NLP TASK TYPES.
    final_labels structure depends on task_type:
    - Sentiment: {"sentiment": "positive"}
    - NER: {"entities": [...]}
    - Topic: {"topic": "finance"}
    """
    
    # One-to-one relationship with NLP chunk
    nlp_chunk = models.OneToOneField(
        "nlp.NLPChunk",
        on_delete=models.CASCADE,
        related_name="consensus",
        help_text="The NLP chunk being consensus'd"
    )
    
    # Task specification
    task_type = models.CharField(
        max_length=50,
        choices=NLPTaskTypeChoices.choices,
        db_index=True,
        help_text="Type of NLP task (sentiment, NER, topic, etc.)"
    )
    
    # Final consensus output - flexible structure for different task types
    final_labels = models.JSONField(
        help_text="Final consensus labels. Structure depends on task_type. "
                  "Sentiment: {'sentiment': 'positive'}. "
                  "NER: {'entities': [...]}. "
                  "Topic: {'topic': 'finance'}."
    )
    
    # Consensus metrics
    agreement_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        help_text="Agreement score among annotators (0-1 scale)"
    )
    
    total_annotations = models.PositiveIntegerField(
        help_text="Number of annotations that contributed to this consensus"
    )
    
    # Workflow
    requires_expert_review = models.BooleanField(
        default=False,
        help_text="Whether this consensus result needs expert review"
    )
    
    computed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the consensus was computed"
    )
    
    class Meta:
        ordering = ["-computed_at"]
        indexes = [
            models.Index(fields=["task_type"]),
            models.Index(fields=["requires_expert_review"]),
            models.Index(fields=["-computed_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(agreement_score__gte=0) & 
                      models.Q(agreement_score__lte=1),
                name="nlp_consensus_agreement_score_valid",
                violation_error_message="agreement_score must be between 0 and 1"
            ),
            models.CheckConstraint(
                check=models.Q(total_annotations__gt=0),
                name="nlp_consensus_total_annotations_positive",
                violation_error_message="total_annotations must be greater than 0"
            ),
        ]
    
    def __str__(self):
        return f"NLPConsensus<{self.nlp_chunk_id}:{self.task_type}>"
    
    def save(self, *args, **kwargs):
        """Validate constraints before save."""
        if not (0 <= self.agreement_score <= 1):
            raise ValueError("agreement_score must be between 0 and 1")
        
        if self.total_annotations <= 0:
            raise ValueError("total_annotations must be greater than 0")
        
        super().save(*args, **kwargs)
