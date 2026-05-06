from django.conf import settings
from django.db import models

from apps.common.models.base import TimeStampedModel


class DomainChoices(models.TextChoices):
    HEALTH = "health", "Health"
    EDUCATION = "education", "Education"
    LAW = "law", "Law"
    FINANCE = "finance", "Finance"
    NEWS = "news", "News"
    RELIGION = "religion", "Religion"
    GENERAL = "general", "General"


class DataTypeChoices(models.TextChoices):
    TEXT = "text", "Text"


class ProcessingStatusChoices(models.TextChoices):
    """Technical pipeline states."""
    PENDING = "pending", "Pending"          # Document uploaded, not yet processed
    PROCESSING = "processing", "Processing" # Currently being processed
    COMPLETED = "completed", "Completed"    # Processing finished successfully
    FAILED = "failed", "Failed"             # Processing failed (e.g., extraction error)


class ReviewStatusChoices(models.TextChoices):
    """Business-level review states."""
    PENDING_REVIEW = "pending_review", "Pending Review" # Waiting for validation
    IN_REVIEW = "in_review", "In Review"                 # Under human/AI validation
    APPROVED = "approved", "Approved"                   # Accepted for dataset use
    REJECTED = "rejected", "Rejected"                   # Not suitable for platform use


class RawDocument(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="raw_documents"
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    domain = models.CharField(
        max_length=20,
        choices=DomainChoices.choices,
        default=DomainChoices.GENERAL
    )
    subdomain = models.CharField(max_length=100, blank=True)

    language = models.CharField(max_length=50, default="amharic")
    data_type = models.CharField(
        max_length=20,
        choices=DataTypeChoices.choices,
        default=DataTypeChoices.TEXT
    )

    consent_given = models.BooleanField(default=False)

    validation_notes = models.TextField(
        blank=True,
        help_text="Populated by the async metadata validator (e.g. Groq) with a human-readable reason."
    )

    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatusChoices.choices,
        default=ProcessingStatusChoices.PENDING
    )
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatusChoices.choices,
        default=ReviewStatusChoices.PENDING_REVIEW
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["processing_status"]),
            models.Index(fields=["review_status"]),
            models.Index(fields=["domain"]),
        ]

    def __str__(self):
        return f"{self.title} (Proc: {self.processing_status}, Rev: {self.review_status})"


class DocumentFile(TimeStampedModel):
    raw_document = models.ForeignKey(
        RawDocument,
        on_delete=models.CASCADE,
        related_name="files"
    )

    file = models.FileField(upload_to="documents/raw/%Y/%m/%d/")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    file_size = models.BigIntegerField()

    checksum = models.CharField(max_length=255, blank=True, null=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self):
        return f"{self.file_name} for {self.raw_document.title}"


class SupportingDocument(TimeStampedModel):
    raw_document = models.ForeignKey(
        RawDocument,
        on_delete=models.CASCADE,
        related_name="supporting_documents"
    )

    file = models.FileField(upload_to="documents/supporting/%Y/%m/%d/")
    file_type = models.CharField(max_length=100)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self):
        return f"Supporting doc for {self.raw_document.title}"
