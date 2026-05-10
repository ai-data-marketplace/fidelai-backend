"""Permissions for the NLP annotation workflow API."""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.nlp.models import NLPAnnotation, NLPAnnotationTask, NLPChunk, NLPTaskAssignment
from apps.nlp.models.choices import NLPTaskAssignmentStatusChoices


class NLPTaskOwnershipPermission(BasePermission):
    message = "You do not have permission to access this NLP resource."

    ACTIVE_ASSIGNMENT_STATUSES = (
        NLPTaskAssignmentStatusChoices.ASSIGNED,
        NLPTaskAssignmentStatusChoices.ACCEPTED,
        NLPTaskAssignmentStatusChoices.IN_PROGRESS,
    )

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user

        if isinstance(obj, NLPTaskAssignment):
            return obj.annotator_id == user.id

        if isinstance(obj, NLPAnnotationTask):
            return obj.assignments.filter(annotator=user).exists()

        if isinstance(obj, NLPChunk):
            return NLPTaskAssignment.objects.filter(
                annotator=user,
                status__in=self.ACTIVE_ASSIGNMENT_STATUSES,
                task__task_chunks__nlp_chunk=obj,
            ).exists()

        if isinstance(obj, NLPAnnotation):
            return obj.annotator_id == user.id

        return False
