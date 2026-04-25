import uuid

from django.db import models

from apps.users.models.roles import RoleChoices

from .choices import ScoreActionTypeChoices


class ScoreLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="score_logs",
    )
    role = models.CharField(max_length=20, choices=RoleChoices.choices)
    action_type = models.CharField(max_length=64, choices=ScoreActionTypeChoices.choices)
    points = models.IntegerField()

    document = models.ForeignKey(
        "documents.RawDocument",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="score_logs",
    )
    chunk = models.ForeignKey(
        "processing.Chunk",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="score_logs",
    )
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="score_logs",
    )

    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        default_permissions = ("add", "view")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    role__in=[
                        RoleChoices.CONTRIBUTOR,
                        RoleChoices.ANNOTATOR,
                        RoleChoices.EXPERT,
                    ]
                ),
                name="chk_score_log_role_scoring_only",
            ),
        ]
        indexes = [
            # user_id already has an index from the ForeignKey definition.
            models.Index(fields=["role"]),
            models.Index(fields=["action_type"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"ScoreLog<{self.user_id}:{self.action_type}:{self.points}>"