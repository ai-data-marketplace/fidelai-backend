"""
NLP task models - Task and task assignment management.

NLPAnnotationTask represents batches of NLP chunks to be annotated.
NLPTaskChunk is a bridge table linking tasks to chunks with ordering.
"""

from django.conf import settings
from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.nlp.models.choices import NLPTaskTypeChoices


class NLPAnnotationTask(TimeStampedModel):
    """
    Represents a batch of NLP chunks for annotation.
    
    Similar to QC AnnotationTask but task-specific for NLP annotation.
    Groups related NLP chunks by task type and domain.
    """
    
    # Task specification
    task_type = models.CharField(
        max_length=50,
        choices=NLPTaskTypeChoices.choices,
        db_index=True,
        help_text="Which NLP task type this batch is for"
    )
    
    name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this task batch"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the task and annotation guidelines"
    )
    
    # Scope
    domain = models.CharField(
        max_length=50,
        blank=True,
        help_text="Domain scope (health, finance, law, etc.) for this task"
    )
    
    # Tracking
    total_chunks = models.PositiveIntegerField(
        default=0,
        help_text="Total number of NLP chunks in this task"
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_nlp_tasks",
        help_text="The user who created this task"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this task is active for assignment"
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task_type"]),
            models.Index(fields=["domain"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["is_active", "task_type"]),
        ]
    
    def __str__(self):
        return f"NLPTask<{self.task_type}:{self.name}>"


class NLPTaskChunk(models.Model):
    """
    Bridge table linking NLPAnnotationTask to NLPChunk.
    
    Represents the relationship between a task and its constituent chunks.
    Ensures each chunk appears only once per task and maintains ordering.
    """
    
    task = models.ForeignKey(
        NLPAnnotationTask,
        on_delete=models.CASCADE,
        related_name="task_chunks",
        help_text="The NLP annotation task"
    )
    
    nlp_chunk = models.ForeignKey(
        "nlp.NLPChunk",
        on_delete=models.CASCADE,
        related_name="task_assignments",
        help_text="The NLP chunk in this task"
    )
    
    order_index = models.PositiveIntegerField(
        help_text="Order/position of this chunk within the task"
    )
    
    class Meta:
        ordering = ["task", "order_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "nlp_chunk"],
                name="uniq_nlp_task_chunk_task_chunk"
            ),
            models.UniqueConstraint(
                fields=["task", "order_index"],
                name="uniq_nlp_task_chunk_order"
            ),
        ]
        indexes = [
            models.Index(fields=["task", "order_index"]),
        ]
    
    def __str__(self):
        return f"NLPTaskChunk<{self.task_id}:{self.nlp_chunk_id}>"
