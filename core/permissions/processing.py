from rest_framework.permissions import BasePermission

from apps.users.models import RoleChoices
from apps.users.models.applications import RoleApplication
from apps.users.models.roles import RoleApplicationStatusChoices


class IsAnnotator(BasePermission):
    message = "You do not have permission to access this assignment."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_verified
            and user.role == RoleChoices.ANNOTATOR
        )


class IsAssignmentOwner(BasePermission):
    message = "You do not have permission to access this assignment."

    def has_object_permission(self, request, view, obj):
        return bool(obj and obj.annotator_id == request.user.id)


class IsExpert(BasePermission):
    message = "User must be an approved expert."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and RoleApplication.objects.filter(
                user=user,
                role_applied_for=RoleChoices.EXPERT,
                status=RoleApplicationStatusChoices.APPROVED,
            ).exists()
        )