from django.contrib.auth.base_user import BaseUserManager
from django.utils.text import slugify

from apps.users.models.roles import RoleChoices


class CustomUserManager(BaseUserManager):
    use_in_migrations = True

    def _generate_username(self, email):
        base_username = slugify(email.split("@")[0]) or "user"
        username = base_username
        suffix = 1

        while self.model.objects.filter(username=username).exists():
            username = f"{base_username}{suffix}"
            suffix += 1

        return username

    def create_user(self, email, username=None, full_name=None, password=None, **extra_fields):
        if not email:
            raise ValueError("The email field is required.")
        if not full_name:
            raise ValueError("The full_name field is required.")

        email = self.normalize_email(email)
        username = username or self._generate_username(email)
        extra_fields.setdefault("is_active", True)

        user = self.model(
            email=email,
            username=username,
            full_name=full_name,
            **extra_fields,
        )

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email, username=None, full_name=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("role", RoleChoices.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if not password:
            raise ValueError("Superuser must have a password.")

        return self.create_user(email, username, full_name, password, **extra_fields)
