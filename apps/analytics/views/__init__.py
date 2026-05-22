from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.serializers import AnnotatorOverviewResponseSerializer, AnnotatorDashboardResponseSerializer, ContributorDashboardResponseSerializer
from apps.analytics.services.annotator_analytics_service import AnnotatorAnalyticsService
from apps.users.models import RoleChoices


class AnnotatorOverviewAnalyticsView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(responses={200: AnnotatorOverviewResponseSerializer})
	def get(self, request):
		if request.user.role != RoleChoices.ANNOTATOR:
			return Response({"detail": "Only annotators can access this endpoint."}, status=403)

		data = AnnotatorAnalyticsService(request.user).get_overview()
		response_payload = {
			"cards": data["cards"],
			"graphs": data["graphs"],
		}
		return Response(response_payload, status=200)


class AnnotatorDashboardView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(responses={200: AnnotatorDashboardResponseSerializer})
	def get(self, request):
		if request.user.role != RoleChoices.ANNOTATOR:
			return Response({"detail": "Only annotators can access this endpoint."}, status=403)

		data = AnnotatorAnalyticsService(request.user).get_dashboard()
		return Response(data, status=200)


class ContributorDashboardView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(responses={200: ContributorDashboardResponseSerializer})
	def get(self, request):
		if request.user.role != RoleChoices.CONTRIBUTOR:
			return Response({"detail": "Only contributors can access this endpoint."}, status=403)

		data = AnnotatorAnalyticsService(request.user).get_contributor_dashboard()
		return Response(data, status=200)


__all__ = ["AnnotatorOverviewAnalyticsView", "AnnotatorDashboardView", "ContributorDashboardView"]
