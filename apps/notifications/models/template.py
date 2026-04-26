from django.db import models

from apps.common.models.base import TimeStampedModel

from .choices import NotificationCategoryChoices, NotificationTypeChoices


class NotificationTemplate(TimeStampedModel):
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationTypeChoices.choices,
    )
    category = models.CharField(
        max_length=20,
        choices=NotificationCategoryChoices.choices,
    )
    title_template = models.CharField(max_length=255)
    message_template = models.TextField()
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("notification_type", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["notification_type"],
                condition=models.Q(active=True),
                name="uniq_active_notification_template_per_type",
            ),
        ]
        indexes = [
            models.Index(fields=["notification_type"]),
            models.Index(fields=["category"]),
            models.Index(fields=["active"]),
        ]

    def __str__(self):
        return f"NotificationTemplate<{self.notification_type}:{self.active}>"