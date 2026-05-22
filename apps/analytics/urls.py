from django.urls import path
from apps.analytics.views import AnnotatorOverviewAnalyticsView
from apps.analytics.views import AnnotatorDashboardView
from apps.analytics.views import ContributorDashboardView
from apps.analytics.views import ExpertOverviewAnalyticsView
from apps.analytics.views import ExpertDashboardView
from apps.analytics.views import AdminDashboardView
from apps.analytics.views import BuyerDashboardView

urlpatterns = [
	path("annotator/overview/", AnnotatorOverviewAnalyticsView.as_view(), name="annotator-overview-analytics"),
	path("annotator/dashboard/", AnnotatorDashboardView.as_view(), name="annotator-dashboard"),
	path("contributor/dashboard/", ContributorDashboardView.as_view(), name="contributor-dashboard"),
	path("expert/overview/", ExpertOverviewAnalyticsView.as_view(), name="expert-overview-analytics"),
	path("expert/dashboard/", ExpertDashboardView.as_view(), name="expert-dashboard"),
	path("admin/dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
	path("buyer/dashboard/", BuyerDashboardView.as_view(), name="buyer-dashboard"),
]
