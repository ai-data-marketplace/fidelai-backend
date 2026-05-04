from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.utils import extend_schema

from apps.scoring.models import ScoreConfig, ScoreLog, UserScore
from core.permissions.processing import IsAdmin
from .serializers import ScoreConfigSerializer, UserScoreSerializer, ScoreLogSerializer


class ScoreConfigViewSet(viewsets.ModelViewSet):
	queryset = ScoreConfig.objects.all()
	serializer_class = ScoreConfigSerializer
	permission_classes = [IsAdmin]


class RecentLogsPagination(PageNumberPagination):
	page_size = 25
	page_size_query_param = "page_size"
	max_page_size = 100


class MyScoreView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(responses={200: UserScoreSerializer})
	def get(self, request):
		user = request.user

		user_score, _ = UserScore.objects.get_or_create(user=user)

		logs_qs = ScoreLog.objects.filter(user=user).order_by("-created_at")

		paginator = RecentLogsPagination()
		page = paginator.paginate_queryset(logs_qs, request)
		logs_serialized = ScoreLogSerializer(page, many=True).data

		return paginator.get_paginated_response({
			"score": UserScoreSerializer(user_score).data,
			"recent_logs": logs_serialized,
		})
