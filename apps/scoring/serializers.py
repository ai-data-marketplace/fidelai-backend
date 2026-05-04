from rest_framework import serializers

from apps.scoring.models import ScoreConfig, UserScore, ScoreLog


class ScoreConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoreConfig
        fields = ["id", "action_type", "points_value", "description"]

    def validate_points_value(self, value):
        if value == 0:
            raise serializers.ValidationError("Points cannot be zero")
        return value


class UserScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserScore
        fields = ["total_points", "updated_at"]


class ScoreLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoreLog
        fields = [
            "id",
            "action_type",
            "points",
            "role",
            "chunk",
            "document",
            "dataset",
            "created_at",
        ]
