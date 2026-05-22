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


class DashboardHighlightSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    display_value = serializers.CharField()


class RecentActivitySerializer(serializers.Serializer):
    id = serializers.CharField()
    task_name = serializers.CharField()
    status = serializers.CharField()
    assigned_at = serializers.CharField()
    completed_at = serializers.CharField(allow_null=True)


class AnnotatorDashboardResponseSerializer(serializers.Serializer):
    highlights = DashboardHighlightSerializer(many=True)
    recent_activity = RecentActivitySerializer(many=True)


class ContributorCardSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.FloatField()
    display_value = serializers.CharField()


class ContributorSubmissionTrendSerializer(serializers.Serializer):
    period = serializers.CharField()
    total_submissions = serializers.IntegerField()
    pending_review = serializers.IntegerField()
    approved = serializers.IntegerField()
    rejected = serializers.IntegerField()


class ContributorDashboardGraphsSerializer(serializers.Serializer):
    submissions_over_time = ContributorSubmissionTrendSerializer(many=True)


class ContributorDashboardResponseSerializer(serializers.Serializer):
    cards = ContributorCardSerializer(many=True)
    graphs = ContributorDashboardGraphsSerializer()


class ExpertCardSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.FloatField()
    display_value = serializers.CharField()


class ExpertReviewTrendSerializer(serializers.Serializer):
    period = serializers.CharField()
    total_reviews = serializers.IntegerField()


class ExpertDashboardGraphsSerializer(serializers.Serializer):
    review_trend = ExpertReviewTrendSerializer(many=True)


class ExpertOverviewResponseSerializer(serializers.Serializer):
    cards = ExpertCardSerializer(many=True)
    graphs = ExpertDashboardGraphsSerializer()


class ExpertDashboardResponseSerializer(serializers.Serializer):
    highlights = DashboardHighlightSerializer(many=True)
    recent_activity = RecentActivitySerializer(many=True)


class AdminRecentActivitySerializer(serializers.Serializer):
    id = serializers.CharField()
    activity_type = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    timestamp = serializers.CharField(allow_null=True)


class AdminDashboardResponseSerializer(serializers.Serializer):
    cards = CardMetricSerializer(many=True)
    recent_activity = AdminRecentActivitySerializer(many=True)


__all__ = [
    "AnnotatorOverviewResponseSerializer",
    "AnnotatorDashboardResponseSerializer",
    "ContributorDashboardResponseSerializer",
    "ExpertOverviewResponseSerializer",
    "ExpertDashboardResponseSerializer",
    "AdminDashboardResponseSerializer",
]
