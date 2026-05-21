from rest_framework import serializers


class MetricDeltaSerializer(serializers.Serializer):
    value = serializers.FloatField()
    label = serializers.CharField()


class CardMetricSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.FloatField()
    display_value = serializers.CharField()
    delta = MetricDeltaSerializer(required=False, allow_null=True)


class TimelinePointSerializer(serializers.Serializer):
    period = serializers.CharField()
    tasks_completed = serializers.IntegerField()
    points_earned = serializers.IntegerField()


class DistributionPointSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.IntegerField()


class AvgTimePointSerializer(serializers.Serializer):
    period = serializers.CharField()
    avg_time_minutes = serializers.FloatField()


class AnnotatorOverviewGraphSerializer(serializers.Serializer):
    weekly_performance = TimelinePointSerializer(many=True)
    confidence_distribution = DistributionPointSerializer(many=True)
    readability_distribution = DistributionPointSerializer(many=True)
    avg_time_trend = AvgTimePointSerializer(many=True)


class AnnotatorOverviewResponseSerializer(serializers.Serializer):
    cards = CardMetricSerializer(many=True)
    graphs = AnnotatorOverviewGraphSerializer()
