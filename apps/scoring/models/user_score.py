from django.db import models


class UserScore(models.Model):
    user = models.OneToOneField(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="user_score",
    )
    total_points = models.IntegerField(default=0)
    locked_points = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-total_points", "-updated_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_points__gte=0),
                name="chk_user_score_total_points_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(locked_points__gte=0),
                name="chk_user_score_locked_points_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["total_points"]),
            models.Index(fields=["updated_at"]),
        ]

    @property
    def available_points(self) -> int:
        """Withdrawable points = total - locked."""
        return max(0, self.total_points - self.locked_points)

    def __str__(self):
        return f"UserScore<{self.user_id}:{self.total_points}>"