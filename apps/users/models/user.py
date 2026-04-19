from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.users.managers import CustomUserManager
from .roles import RoleChoices, TimeStampedModel


class CustomUser(TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    phone_number = models.CharField(max_length=20, blank=True)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=RoleChoices.choices, default=RoleChoices.UNKNOWN)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    is_locked = models.BooleanField(default=False)
    lock_until = models.DateTimeField(blank=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ("-date_joined",)

    def __str__(self):
        return self.email


class EmailVerificationCode(TimeStampedModel):
    user = models.ForeignKey("users.CustomUser", on_delete=models.CASCADE, related_name="verification_codes")
    code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"EmailVerificationCode<{self.user.email}:{self.code}>"
