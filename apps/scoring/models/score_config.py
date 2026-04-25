from django.db import models

from .choices import ScoreActionTypeChoices


class ScoreConfig(models.Model):
    action_type = models.CharField(
        max_length=64,
        unique=True,
        choices=ScoreActionTypeChoices.choices,
    )
    points_value = models.IntegerField()
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("action_type",)

    def __str__(self):
        return f"ScoreConfig<{self.action_type}:{self.points_value}>"