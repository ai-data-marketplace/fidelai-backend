from django.db import models


class UserScore(models.Model):
    user = models.OneToOneField(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="user_score",
    )
    total_points = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-total_points", "-updated_at")
        indexes = [
            models.Index(fields=["total_points"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return f"UserScore<{self.user_id}:{self.total_points}>"