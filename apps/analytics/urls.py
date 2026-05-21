from django.urls import path
from apps.analytics.views import AnnotatorOverviewAnalyticsView

urlpatterns = [
	path("annotator/overview/", AnnotatorOverviewAnalyticsView.as_view(), name="annotator-overview-analytics"),
]
