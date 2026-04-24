from django.db import models


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
