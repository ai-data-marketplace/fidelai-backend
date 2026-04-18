import uuid

from django.db import models


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class RoleChoices(models.TextChoices):
    CONTRIBUTOR = "contributor", "contributor"
    ANNOTATOR = "annotator", "annotator"
    EXPERT = "expert", "expert reviewer"
    BUYER = "buyer", "buyer"
    ADMIN = "admin", "admin"
    UNKNOWN = "unknown", "unknown"
    


class RoleApplicationStatusChoices(models.TextChoices):
    PENDING = "pending", "pending"
    APPROVED = "approved", "approved"
    REJECTED = "rejected", "rejected"
