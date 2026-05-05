from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import CustomUser, RoleApplication, RoleApplicationStatusChoices
from apps.users.serializers.role_management import AdminUserListSerializer, RoleApplicationAdminSerializer
from core.permissions.processing import IsAdmin


class RoleApplicationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    get=extend_schema(
        responses={200: RoleApplicationAdminSerializer(many=True)},
        description="List pending role applications for admin review.",
    )
)
class PendingRoleApplicationListView(generics.ListAPIView):
    serializer_class = RoleApplicationAdminSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = RoleApplicationPagination

    def get_queryset(self):
        return (
            RoleApplication.objects.select_related("user", "reviewed_by")
            .filter(status=RoleApplicationStatusChoices.PENDING)
            .order_by("-submitted_at")
        )


@extend_schema_view(
    get=extend_schema(
        responses={200: AdminUserListSerializer(many=True)},
        description="List users for admin review.",
    )
)
class AdminUserListView(generics.ListAPIView):
    serializer_class = AdminUserListSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = RoleApplicationPagination

    def get_queryset(self):
        return CustomUser.objects.all().order_by("-date_joined")


class _BaseRoleApplicationDecisionView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_application(self, pk):
        return (
            RoleApplication.objects.select_related("user", "reviewed_by")
            .filter(pk=pk)
            .first()
        )

    def _handle_non_pending(self, application):
        if application.status != RoleApplicationStatusChoices.PENDING:
            return Response(
                {"detail": "Role application has already been reviewed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None


class ApproveRoleApplicationView(_BaseRoleApplicationDecisionView):
    @extend_schema(
        request=None,
        responses={200: RoleApplicationAdminSerializer},
        description="Approve a pending role application and assign the requested role to the user.",
    )
    def post(self, request, pk):
        application = self._get_application(pk)
        if not application:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        invalid_response = self._handle_non_pending(application)
        if invalid_response:
            return invalid_response

        with transaction.atomic():
            application = RoleApplication.objects.select_for_update().select_related("user", "reviewed_by").get(pk=application.pk)
            if application.status != RoleApplicationStatusChoices.PENDING:
                return Response(
                    {"detail": "Role application has already been reviewed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            application.status = RoleApplicationStatusChoices.APPROVED
            application.reviewed_at = timezone.now()
            application.reviewed_by = request.user
            application.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])

            user = application.user
            user.role = application.role_applied_for
            user.save(update_fields=["role", "updated_at"])

        return Response(RoleApplicationAdminSerializer(application).data, status=status.HTTP_200_OK)


class RejectRoleApplicationView(_BaseRoleApplicationDecisionView):
    @extend_schema(
        request=None,
        responses={200: RoleApplicationAdminSerializer},
        description="Reject a pending role application.",
    )
    def post(self, request, pk):
        application = self._get_application(pk)
        if not application:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        invalid_response = self._handle_non_pending(application)
        if invalid_response:
            return invalid_response

        with transaction.atomic():
            application = RoleApplication.objects.select_for_update().select_related("user", "reviewed_by").get(pk=application.pk)
            if application.status != RoleApplicationStatusChoices.PENDING:
                return Response(
                    {"detail": "Role application has already been reviewed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            application.status = RoleApplicationStatusChoices.REJECTED
            application.reviewed_at = timezone.now()
            application.reviewed_by = request.user
            application.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])

        return Response(RoleApplicationAdminSerializer(application).data, status=status.HTTP_200_OK)