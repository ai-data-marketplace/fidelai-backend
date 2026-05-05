from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.models import Notification, NotificationCategoryChoices
from apps.notifications.serializers import NotificationSerializer


class NotificationPagination(PageNumberPagination):
	page_size = 20
	page_size_query_param = "page_size"
	max_page_size = 100


def _parse_bool(value: str | None):
	if value is None:
		return None

	normalized = value.strip().lower()
	if normalized in {"1", "true", "t", "yes", "y"}:
		return True
	if normalized in {"0", "false", "f", "no", "n"}:
		return False
	raise ValidationError({"detail": "Invalid boolean filter value."})


class NotificationListView(generics.ListAPIView):
	serializer_class = NotificationSerializer
	permission_classes = [IsAuthenticated]
	pagination_class = NotificationPagination

	def get_queryset(self):
		queryset = Notification.objects.filter(user=self.request.user).order_by("-created_at")

		is_read = _parse_bool(self.request.query_params.get("is_read"))
		if is_read is not None:
			queryset = queryset.filter(is_read=is_read)

		category = self.request.query_params.get("category")
		if category:
			if category not in NotificationCategoryChoices.values:
				raise ValidationError({"detail": "Invalid notification category filter."})
			queryset = queryset.filter(category=category)

		return queryset


class MarkNotificationReadView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request, pk):
		try:
			notification = Notification.objects.get(id=pk, user=request.user)
		except Notification.DoesNotExist:
			return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

		if not notification.is_read:
			notification.is_read = True
			notification.read_at = timezone.now()
			notification.save(update_fields=["is_read", "read_at"])

		return Response({"detail": "Marked as read"}, status=status.HTTP_200_OK)


class MarkAllNotificationsReadView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request):
		Notification.objects.filter(user=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
		return Response({"detail": "All notifications marked as read"}, status=status.HTTP_200_OK)


class UnreadCountView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		count = Notification.objects.filter(user=request.user, is_read=False).count()
		return Response({"unread_count": count}, status=status.HTTP_200_OK)
