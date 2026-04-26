from django.db import models

from apps.common.models.base import TimeStampedModel

from .choices import NotificationCategoryChoices, NotificationTypeChoices


class Notification(TimeStampedModel):
    user = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=20, choices=NotificationCategoryChoices.choices)
    notification_type = models.CharField(max_length=50, choices=NotificationTypeChoices.choices)

    title = models.CharField(max_length=255)
    message = models.TextField()
    metadata = models.JSONField(blank=True, null=True)

    in_app_sent = models.BooleanField(default=True)
    email_sent = models.BooleanField(default=False)

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)

    related_task = models.ForeignKey(
        "processing.AnnotationTask",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="notifications",
    )
    related_dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="notifications",
    )
    related_order = models.ForeignKey(
        "marketplace.Order",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="notifications",
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(is_read=True, read_at__isnull=False)
                    | models.Q(is_read=False, read_at__isnull=True)
                ),
                name="chk_notification_read_state_consistent",
            ),
        ]
        indexes = [
            # user_id is indexed by Django ForeignKey automatically.
            models.Index(fields=["category"]),
            models.Index(fields=["notification_type"]),
            models.Index(fields=["is_read"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["user", "is_read", "created_at"]),
            models.Index(fields=["user", "category", "created_at"]),
        ]

    def __str__(self):
        return f"Notification<{self.user_id}:{self.notification_type}:{self.is_read}>"