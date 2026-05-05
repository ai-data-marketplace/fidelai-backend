from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "category",
            "notification_type",
            "title",
            "message",
            "metadata",
            "is_read",
            "read_at",
            "created_at",
        ]