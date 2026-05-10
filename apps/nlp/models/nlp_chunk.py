"""
NLPChunk model - Task-specific NLP-ready annotation units.

NLPChunk is NOT the same as processing.Chunk:
- Smaller, task-oriented units extracted from QC-approved chunks
- Generated from APPROVED chunks in the processing pipeline
- Intended for NLP-specific annotation (sentiment, NER, topic, etc.)
- Preserves full linkage to source QC chunk for traceability
"""

from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.processing.models.chunk import Chunk
from apps.nlp.models.choices import NLPTaskTypeChoices, NLPChunkStatusChoices


class NLPChunk(TimeStampedModel):
    """
    Represents an NLP-task-ready annotation unit extracted from a QC-approved chunk.
    
    Similar to processing.Chunk but:
    - Smaller and task-oriented
    - Linked to original chunk for full traceability
    - Contains AI extraction metadata
    - Requires surrounding context for annotation clarity
    """
    
    # Source linkage - preserve traceability to original QC chunk
    source_chunk = models.ForeignKey(
        Chunk,
        on_delete=models.CASCADE,
        related_name="nlp_chunks",
        help_text="The QC-approved chunk this NLP unit was extracted from"
    )
    
    # Task type - which NLP task this chunk is for
    task_type = models.CharField(
        max_length=50,
        choices=NLPTaskTypeChoices.choices,
        db_index=True,
        help_text="The NLP task this chunk is designated for"
    )
    
    # Core content
    text = models.TextField(
        help_text="The actual text content for NLP annotation"
    )
    
    # Text positioning within source chunk
    order_index = models.PositiveIntegerField(
        help_text="Order of this NLP unit within the NLP chunks from source chunk"
    )
    char_start = models.PositiveIntegerField(
        help_text="Character offset start position in source chunk text"
    )
    char_end = models.PositiveIntegerField(
        help_text="Character offset end position in source chunk text"
    )
    
    # Metadata - flexible storage for task-specific metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Flexible metadata storage for task-specific information"
    )
    
    # AI extraction information
    generated_by_ai = models.BooleanField(
        default=False,
        help_text="Whether this chunk was AI-extracted or manually created"
    )
    ai_model_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Name of AI model used for extraction (if generated_by_ai=True)"
    )
    ai_confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        blank=True,
        null=True,
        help_text="Confidence score of AI extraction (0-1 scale)"
    )
    
    # Context for annotation clarity
    source_context = models.TextField(
        blank=True,
        help_text="Surrounding context from source chunk for annotation clarity"
    )
    source_domain = models.CharField(
        max_length=50,
        blank=True,
        help_text="Domain of source document (health, finance, law, etc.)"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=30,
        choices=NLPChunkStatusChoices.choices,
        default=NLPChunkStatusChoices.PENDING_EXTRACTION,
        db_index=True,
        help_text="Lifecycle status of this NLP chunk"
    )
    
    # Quality tracking
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this chunk is active for annotation"
    )
    requires_human_review = models.BooleanField(
        default=False,
        help_text="Whether this chunk needs human review (e.g., from AI extraction)"
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source_chunk", "task_type"]),
            models.Index(fields=["task_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["source_chunk"]),
            models.Index(fields=["source_domain"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["is_active", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(char_end__gt=models.F("char_start")),
                name="nlp_chunk_char_end_gt_start",
                violation_error_message="char_end must be greater than char_start"
            ),
            models.CheckConstraint(
                check=models.Q(ai_confidence_score__isnull=True) | 
                      models.Q(ai_confidence_score__gte=0) & 
                      models.Q(ai_confidence_score__lte=1),
                name="nlp_chunk_confidence_score_valid",
                violation_error_message="ai_confidence_score must be between 0 and 1 or NULL"
            ),
        ]
    
    def __str__(self):
        return f"NLPChunk<{self.source_chunk_id}:{self.task_type}:{self.id}>"
    
    def save(self, *args, **kwargs):
        """Validate constraints before save."""
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        
        if self.ai_confidence_score is not None:
            if not (0 <= self.ai_confidence_score <= 1):
                raise ValueError("ai_confidence_score must be between 0 and 1")
        
        super().save(*args, **kwargs)
