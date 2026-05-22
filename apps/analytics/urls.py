from django.urls import path
from apps.analytics.views import AnnotatorOverviewAnalyticsView
from apps.analytics.views import AnnotatorDashboardView
from apps.analytics.views import ContributorDashboardView

urlpatterns = [
	path("annotator/overview/", AnnotatorOverviewAnalyticsView.as_view(), name="annotator-overview-analytics"),
	path("annotator/dashboard/", AnnotatorDashboardView.as_view(), name="annotator-dashboard"),
	path("contributor/dashboard/", ContributorDashboardView.as_view(), name="contributor-dashboard"),
]
