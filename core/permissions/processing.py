from rest_framework.permissions import BasePermission

from apps.users.models import RoleChoices


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