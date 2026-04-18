from django.conf import settings
from django.db import models

from .roles import RoleApplicationStatusChoices, RoleChoices, TimeStampedModel


class RoleApplication(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_applications")
    role_applied_for = models.CharField(max_length=20, choices=RoleChoices.choices)
    # Raw role-specific onboarding payload from step-2.
    application_data = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=RoleApplicationStatusChoices.choices,
        default=RoleApplicationStatusChoices.PENDING,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_role_applications",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("-submitted_at",)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["role_applied_for"]),
        ]

    def __str__(self):
        return f"RoleApplication<{self.user.email}:{self.role_applied_for}>"


class VerificationDocument(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="verification_documents")
    role_application = models.ForeignKey(
        RoleApplication,
        on_delete=models.SET_NULL,
        related_name="documents",
        blank=True,
        null=True,
    )
    file = models.FileField(upload_to="users/verification_documents/")
    file_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    purpose = models.CharField(max_length=255)
    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self):
        return f"VerificationDocument<{self.user.email}:{self.file_type}:{self.purpose}>"