from rest_framework import serializers


class DashboardHighlightSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    display_value = serializers.CharField()


class RecentActivitySerializer(serializers.Serializer):
    id = serializers.CharField()
    chunk_id = serializers.CharField()
    chunk_text = serializers.CharField()
    task_name = serializers.CharField()
    domain_match = serializers.CharField()
    confidence = serializers.CharField()
    readability = serializers.CharField()
    safety_label = serializers.CharField()
    created_at = serializers.CharField()
    is_skipped = serializers.BooleanField()


class AnnotatorDashboardResponseSerializer(serializers.Serializer):
    highlights = DashboardHighlightSerializer(many=True)
    recent_activity = RecentActivitySerializer(many=True)
