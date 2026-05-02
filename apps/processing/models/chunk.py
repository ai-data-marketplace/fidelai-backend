from django.db import models

from apps.common.models.base import TimeStampedModel


class DomainMatchChoices(models.TextChoices):
    MATCH = "match", "Match"
    NOT_MATCH = "not_match", "Not Match"
    UNCERTAIN = "uncertain", "Uncertain"


class ReadabilityChoices(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class SafetyChoices(models.TextChoices):
    SAFE = "safe", "Safe"
    UNSAFE = "unsafe", "Unsafe"


class ConfidenceChoices(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class TaskAssignmentStatusChoices(models.TextChoices):
    ASSIGNED = "assigned", "Assigned"
    ACCEPTED = "accepted", "Accepted"
    IN_PROGRESS = "in_progress", "In Progress"
    SUBMITTED = "submitted", "Submitted"
    DECLINED = "declined", "Declined"


class ChunkStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending"
    AI_PROCESSED = "ai_processed", "AI Processed"
    IN_ANNOTATION = "in_annotation", "In Annotation"
    ANNOTATED = "annotated", "Annotated"
    CONSENSUS_READY = "consensus_ready", "Consensus Ready"
    ESCALATED = "escalated", "Escalated"
    RESOLVED = "resolved", "Resolved"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ExtractedDocument(TimeStampedModel):
    raw_document = models.OneToOneField(
        "documents.RawDocument",
        on_delete=models.CASCADE,
        related_name="extracted_document",
    )
    full_text = models.TextField()
    structure = models.JSONField(default=list)
    layout_metadata = models.JSONField(default=dict, blank=True, null=True)
    language_detected = models.CharField(max_length=32, default="amharic")
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    similarity_signature = models.JSONField(blank=True, null=True)
    processed_at = models.DateTimeField()

    class Meta:
        ordering = ("-processed_at",)
        indexes = [
            models.Index(fields=["processed_at"]),
            models.Index(fields=["language_detected"]),
        ]

    def __str__(self):
        return f"ExtractedDocument<{self.raw_document_id}>"

    @property
    def extracted_text(self):
        return self.full_text

    @property
    def extraction_metadata(self):
        return self.layout_metadata


class Chunk(TimeStampedModel):
    extracted_document = models.ForeignKey(
        ExtractedDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    status = models.CharField(
        max_length=20,
        choices=ChunkStatusChoices.choices,
        default=ChunkStatusChoices.PENDING,
    )
    text = models.TextField()
    order_index = models.PositiveIntegerField()
    char_start = models.PositiveIntegerField()
    char_end = models.PositiveIntegerField()
    token_count = models.PositiveIntegerField()
    quality_score = models.FloatField(default=0.0, db_index=True)
    metadata = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ("extracted_document", "order_index")
        constraints = [
            models.UniqueConstraint(
                fields=["extracted_document", "order_index"],
                name="uniq_chunk_extracted_document_order",
            ),
            models.CheckConstraint(
                condition=models.Q(char_end__gt=models.F("char_start")),
                name="chk_chunk_char_end_gt_start",
            ),
        ]
        indexes = [
            models.Index(fields=["extracted_document"]),
            models.Index(fields=["status"]),
            models.Index(fields=["order_index"]),
            models.Index(fields=["extracted_document", "order_index"]),
        ]

    def __str__(self):
        return f"Chunk<{self.extracted_document_id}:{self.order_index}>"
