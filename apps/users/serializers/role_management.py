from rest_framework import serializers

from apps.users.models import CustomUser, RoleApplication


class RoleApplicationUserSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)


class RoleApplicationAdminSerializer(serializers.ModelSerializer):
    user = RoleApplicationUserSummarySerializer(read_only=True)
    reviewed_by = RoleApplicationUserSummarySerializer(read_only=True)

    class Meta:
        model = RoleApplication
        fields = [
            "id",
            "user",
            "role_applied_for",
            "application_data",
            "status",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
        ]
        read_only_fields = fields


class AdminUserListSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    verification = serializers.BooleanField(source="is_verified", read_only=True)
    joined_date = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            "user",
            "role",
            "status",
            "verification",
            "joined_date",
        ]

    def get_user(self, obj):
        return obj.full_name or obj.email

    def get_status(self, obj):
        return "active" if obj.is_active else "inactive"

