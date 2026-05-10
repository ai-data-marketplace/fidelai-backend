"""
NLP annotation models - Assignments and annotations.

NLPTaskAssignment: Assigns NLP annotation tasks to annotators.
NLPAnnotation: Records individual annotations with flexible label storage.
"""

from django.conf import settings
from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.nlp.models.choices import NLPTaskAssignmentStatusChoices, NLPTaskTypeChoices


class NLPTaskAssignment(TimeStampedModel):
    """
    Represents assignment of an NLP annotation task to an annotator.
    
    Tracks the complete workflow from assignment through completion.
    """
    
    task = models.ForeignKey(
        "nlp.NLPAnnotationTask",
        on_delete=models.CASCADE,
        related_name="assignments",
        help_text="The NLP task being assigned"
    )
    
    annotator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nlp_task_assignments",
        help_text="The annotator assigned to this task"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=NLPTaskAssignmentStatusChoices.choices,
        default=NLPTaskAssignmentStatusChoices.ASSIGNED,
        db_index=True,
        help_text="Current status of this assignment"
    )
    
    # Timeline
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the task was assigned"
    )
    started_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the annotator started work on this task"
    )
    completed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the annotator completed the task"
    )
    
    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "annotator"],
                name="uniq_nlp_assignment_task_annotator"
            ),
        ]
        indexes = [
            models.Index(fields=["annotator"]),
            models.Index(fields=["task"]),
            models.Index(fields=["status"]),
            models.Index(fields=["annotator", "status"]),
        ]
    
    def __str__(self):
        return f"NLPAssignment<{self.task_id}:{self.annotator_id}:{self.status}>"


class NLPAnnotation(TimeStampedModel):
    """
    Records an individual NLP annotation.
    
    CRITICAL DESIGN: This model supports MULTIPLE NLP TASK TYPES.
    Labels are stored as JSONField to support heterogeneous label structures:
    - Sentiment: {"sentiment": "positive"}
    - NER: {"entities": [...]}
    - Topic: {"topic": "finance"}
    
    Do NOT hardcode sentiment-only assumptions.
    """
    
    # Core reference
    nlp_chunk = models.ForeignKey(
        "nlp.NLPChunk",
        on_delete=models.CASCADE,
        related_name="annotations",
        help_text="The NLP chunk being annotated"
    )
    
    annotator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nlp_annotations",
        help_text="The annotator who performed this annotation"
    )
    
    task_assignment = models.ForeignKey(
        NLPTaskAssignment,
        on_delete=models.CASCADE,
        related_name="annotations",
        help_text="The task assignment this annotation is part of"
    )
    
    # Task specification
    task_type = models.CharField(
        max_length=50,
        choices=NLPTaskTypeChoices.choices,
        db_index=True,
        help_text="Type of NLP task (sentiment, NER, topic, etc.)"
    )
    
    # Flexible label storage - supports multiple NLP task types
    labels = models.JSONField(
        help_text="Task-specific labels. Structure depends on task_type. "
                  "Sentiment: {'sentiment': 'positive'}. "
                  "NER: {'entities': [...]}. "
                  "Topic: {'topic': 'finance'}."
    )
    
    # Annotation metadata
    notes = models.TextField(
        blank=True,
        help_text="Annotator notes or reasoning for the label"
    )
    
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        blank=True,
        null=True,
        help_text="Annotator confidence in this annotation (0-1)"
    )
    
    time_spent_seconds = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Seconds spent annotating this chunk"
    )
    
    is_skipped = models.BooleanField(
        default=False,
        help_text="Whether this chunk was skipped during annotation"
    )
    
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["nlp_chunk", "annotator"],
                name="uniq_nlp_annotation_chunk_annotator"
            ),
        ]
        indexes = [
            models.Index(fields=["nlp_chunk"]),
            models.Index(fields=["annotator"]),
            models.Index(fields=["task_type"]),
            models.Index(fields=["nlp_chunk", "annotator"]),
            models.Index(fields=["annotator", "task_type"]),
        ]
    
    def __str__(self):
        return f"NLPAnnotation<{self.nlp_chunk_id}:{self.annotator_id}:{self.task_type}>"
    
    def save(self, *args, **kwargs):
        """Validate confidence score before save."""
        if self.confidence_score is not None:
            if not (0 <= self.confidence_score <= 1):
                raise ValueError("confidence_score must be between 0 and 1 or NULL")
        super().save(*args, **kwargs)
