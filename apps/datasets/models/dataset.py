from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.documents.models import DomainChoices


class DatasetStatusChoices(models.TextChoices):
    DRAFT = "draft", "Draft"
    PROCESSING = "processing", "Processing"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    PUBLISHED = "published", "Published"


class DatasetLicenseChoices(models.TextChoices):
    MIT = "mit", "MIT"
    COMMERCIAL = "commercial", "Commercial"
    CUSTOM = "custom", "Custom"


class Dataset(TimeStampedModel):
    title = models.CharField(max_length=255)
    description = models.TextField()
    domain = models.CharField(max_length=20, choices=DomainChoices.choices)
    subdomain = models.CharField(max_length=100, blank=True)
    language = models.CharField(max_length=50, default="amharic")

    license_type = models.CharField(max_length=20, choices=DatasetLicenseChoices.choices)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    version = models.CharField(max_length=32, default="v1.0")
    status = models.CharField(
        max_length=20,
        choices=DatasetStatusChoices.choices,
        default=DatasetStatusChoices.DRAFT,
    )

    collection_year = models.PositiveIntegerField()
    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        related_name="datasets",
        blank=True,
        null=True,
    )
    approved_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        related_name="approved_datasets",
        blank=True,
        null=True,
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name="chk_dataset_price_non_negative"),
            models.CheckConstraint(
                condition=models.Q(collection_year__gte=1900),
                name="chk_dataset_collection_year_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=DatasetStatusChoices.PUBLISHED, published_at__isnull=False)
                    | ~models.Q(status=DatasetStatusChoices.PUBLISHED)
                ),
                name="chk_dataset_published_requires_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["domain"]),
            models.Index(fields=["subdomain"]),
            models.Index(fields=["price"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["approved_by"]),
            models.Index(fields=["approved_at"]),
            models.Index(fields=["published_at"]),
        ]

    def __str__(self):
        return f"Dataset<{self.title}:{self.version}>"