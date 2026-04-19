import secrets
from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.utils.encoding import force_bytes, force_str
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status

from apps.users.models import CustomUser, EmailVerificationCode, RoleChoices
from core.utils.email import send_password_reset_email, send_verification_email
from core.validators import validate_password_strength


class AuthServiceError(Exception):
    def __init__(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthService:
    CODE_EXPIRY_MINUTES = 10
    LOCK_MINUTES = 15
    MAX_FAILED_ATTEMPTS = 5
    RESEND_SECONDS = 60
    PASSWORD_RESET_TOKEN_GENERATOR = PasswordResetTokenGenerator()

    @staticmethod
    def _generate_6_digit_code():
        return f"{secrets.randbelow(1000000):06d}"

    @classmethod
    def _invalidate_active_codes(cls, user):
        EmailVerificationCode.objects.filter(
            user=user,
            is_used=False,
            expires_at__gt=timezone.now(),
        ).update(is_used=True)

    @classmethod
    def _create_code(cls, user):
        cls._invalidate_active_codes(user)
        code = cls._generate_6_digit_code()
        expires_at = timezone.now() + timedelta(minutes=cls.CODE_EXPIRY_MINUTES)
        return EmailVerificationCode.objects.create(user=user, code=code, expires_at=expires_at)

    @classmethod
    def _latest_active_code(cls, user):
        return (
            EmailVerificationCode.objects.filter(
                user=user,
                is_used=False,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def register(cls, full_name, email, password):
        try:
            validate_password_strength(password)
        except ValueError as exc:
            raise AuthServiceError(str(exc)) from exc
        existing_user = CustomUser.objects.filter(email__iexact=email).first()
        if existing_user:
            raise AuthServiceError(
                "Unable to complete registration with the provided information.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user = CustomUser.objects.create_user(
            email=email,
            full_name=full_name,
            password=password,
            role=RoleChoices.UNKNOWN,
            is_verified=False,
        )

        verification = cls._create_code(user)
        send_verification_email(user, verification.code)
        return user

    @classmethod
    def verify_email_code(cls, email, code):
        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user:
            raise AuthServiceError("Invalid email or code.")

        latest_code = cls._latest_active_code(user)
        if not latest_code:
            raise AuthServiceError("Verification code expired or unavailable.")
        if latest_code.code != code:
            raise AuthServiceError("Invalid verification code.")

        latest_code.is_used = True
        latest_code.save(update_fields=["is_used"])

        if not user.is_verified:
            user.is_verified = True
            user.save(update_fields=["is_verified"])

        return user

    @classmethod
    def resend_verification_code(cls, email):
        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user:
            raise AuthServiceError("User not found.")

        cache_key = f"auth:resend:{email.lower()}"
        if cache.get(cache_key):
            raise AuthServiceError(
                "Please wait before requesting another code.",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        verification = cls._create_code(user)
        send_verification_email(user, verification.code)
        cache.set(cache_key, True, timeout=cls.RESEND_SECONDS)

    @classmethod
    def login(cls, email, password):
        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user:
            raise AuthServiceError("Invalid credentials.", status_code=status.HTTP_401_UNAUTHORIZED)

        now = timezone.now()
        if user.is_locked and user.lock_until and user.lock_until > now:
            raise AuthServiceError(
                "Account is locked. Try again later.",
                status_code=status.HTTP_423_LOCKED,
            )

        if user.is_locked and user.lock_until and user.lock_until <= now:
            user.is_locked = False
            user.lock_until = None
            user.failed_login_attempts = 0
            user.save(update_fields=["is_locked", "lock_until", "failed_login_attempts"])

        authenticated_user = authenticate(username=email, password=password)
        if not authenticated_user:
            user.failed_login_attempts += 1
            update_fields = ["failed_login_attempts"]

            if user.failed_login_attempts >= cls.MAX_FAILED_ATTEMPTS:
                user.is_locked = True
                user.lock_until = now + timedelta(minutes=cls.LOCK_MINUTES)
                update_fields.extend(["is_locked", "lock_until"])

            user.save(update_fields=update_fields)

            if user.is_locked:
                raise AuthServiceError(
                    "Account locked for 15 minutes due to repeated failed logins.",
                    status_code=status.HTTP_423_LOCKED,
                )
            raise AuthServiceError("Invalid credentials.", status_code=status.HTTP_401_UNAUTHORIZED)

        if not authenticated_user.is_verified:
            raise AuthServiceError(
                "Please verify your email before logging in.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        authenticated_user.failed_login_attempts = 0
        authenticated_user.is_locked = False
        authenticated_user.lock_until = None
        authenticated_user.save(update_fields=["failed_login_attempts", "is_locked", "lock_until"])

        return authenticated_user

    @classmethod
    def forgot_password(cls, email):
        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user:
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = cls.PASSWORD_RESET_TOKEN_GENERATOR.make_token(user)
        from django.conf import settings

        frontend_url = settings.FRONTEND_URL.rstrip("/")

        reset_link = f"{frontend_url}/account/reset-password/{uid}/{token}/"
        send_password_reset_email(user, reset_link)

    @classmethod
    def reset_password(cls, uid, token, new_password):
        try:
            validate_password_strength(new_password)
        except ValueError as exc:
            raise AuthServiceError(str(exc)) from exc

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = CustomUser.objects.get(pk=user_id)
        except Exception as exc:
            raise AuthServiceError("Invalid password reset link.") from exc

        if not cls.PASSWORD_RESET_TOKEN_GENERATOR.check_token(user, token):
            raise AuthServiceError("Invalid or expired password reset token.")

        user.set_password(new_password)
        user.save(update_fields=["password"])
