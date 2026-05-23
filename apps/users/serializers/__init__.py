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



class UserProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=False)
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    bio = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)
    native_language = serializers.CharField(required=False, allow_blank=True)
    notification_preferences = serializers.JSONField(required=False)

    def update(self, instance, validated_data):
        # instance can be a UserProfile model instance or a dict containing {'user': user}
        from apps.users.models.profile import UserProfile

        user = None
        profile = None
        if isinstance(instance, dict) and instance.get("user"):
            user = instance.get("user")
            profile = getattr(user, "userprofile", None)
        else:
            profile = instance
            user = getattr(profile, "user", None)

        # update user full_name if provided
        if "full_name" in validated_data and user:
            user.full_name = validated_data.pop("full_name")
            user.save(update_fields=["full_name"])

        # create profile if missing
        if profile is None and user:
            create_data = {k: v for k, v in validated_data.items()}
            profile = UserProfile.objects.create(user=user, **create_data)
            return profile

        # update profile fields
        for key, value in validated_data.items():
            setattr(profile, key, value)
        profile.save()
        return profile

    def create(self, validated_data):
        # Not used directly; kept for serializer.save() compatibility
        raise NotImplementedError()


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
