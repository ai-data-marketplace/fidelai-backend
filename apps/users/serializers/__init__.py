from rest_framework import serializers

from core.validators import validate_password_strength


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        try:
            validate_password_strength(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(r"^\d{6}$", max_length=6, min_length=6)


class ResendCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        try:
            validate_password_strength(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value


class UserSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)


class UserProfileSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    role = serializers.CharField(source="user.role", read_only=True)
    profile_picture = serializers.ImageField(allow_null=True, required=False)
    phone_number = serializers.CharField(allow_blank=True, required=False)
    bio = serializers.CharField(allow_blank=True, required=False)
    country = serializers.CharField(allow_blank=True, required=False)
    native_language = serializers.CharField(allow_blank=True, required=False)
    notification_preferences = serializers.JSONField(required=False)


from .role_management import RoleApplicationAdminSerializer, RoleApplicationUserSummarySerializer

__all__ = [
    "RegisterSerializer",
    "VerifyEmailSerializer",
    "ResendCodeSerializer",
    "LoginSerializer",
    "ForgotPasswordSerializer",
    "ResetPasswordSerializer",
    "UserSerializer",
    "RoleApplicationAdminSerializer",
    "RoleApplicationUserSummarySerializer",
]
