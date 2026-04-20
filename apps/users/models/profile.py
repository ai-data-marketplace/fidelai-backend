from django.conf import settings
from django.db import models

from .roles import TimeStampedModel


class UserProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="userprofile")
    profile_picture = models.ImageField(upload_to="users/profile_pictures/", blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    native_language = models.CharField(max_length=64, blank=True)
    notification_preferences = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Profile<{self.user.email}>"
