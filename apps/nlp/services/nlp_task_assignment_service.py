"""Service for assigning NLP annotation tasks to annotators.

This service keeps task assignment fair, avoids duplicate rows, and caps each
task at three annotators to support downstream consensus workflows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as datetime_timezone
from typing import Dict, Iterable, List, Optional, Sequence

from django.db import IntegrityError, transaction
from django.db.models import Count, DateTimeField, Exists, Max, OuterRef, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.nlp.models import NLPAnnotationTask, NLPTaskAssignment, NLPTaskAssignmentStatusChoices
from apps.users.models import CustomUser, RoleChoices


logger = logging.getLogger(__name__)


class NLPTaskAssignmentService:
    """Assign NLP annotation tasks to annotators."""

    TARGET_ANNOTATORS_PER_TASK = 3
    MAX_ACTIVE_ASSIGNMENTS_PER_ANNOTATOR = 10
    ACTIVE_ASSIGNMENT_STATUSES = (
        NLPTaskAssignmentStatusChoices.ASSIGNED,
        NLPTaskAssignmentStatusChoices.ACCEPTED,
        NLPTaskAssignmentStatusChoices.IN_PROGRESS,
    )
    TASK_FILL_STATUSES = (
        NLPTaskAssignmentStatusChoices.ASSIGNED,
        NLPTaskAssignmentStatusChoices.ACCEPTED,
        NLPTaskAssignmentStatusChoices.IN_PROGRESS,
        NLPTaskAssignmentStatusChoices.SUBMITTED,
    )
    OLDEST_LAST_ASSIGNMENT_AT = datetime(1970, 1, 1, tzinfo=datetime_timezone.utc)

    def assign_tasks(self) -> Dict[str, object]:
        """Assign eligible NLP tasks to annotators.

        Tasks are assigned to up to three annotators, balancing workload across
        all eligible annotators. Existing assignments are preserved and duplicate
        assignments are prevented.
        """
        summary: Dict[str, object] = {
            "tasks_scanned": 0,
            "tasks_assigned": 0,
            "assignments_created": 0,
            "tasks_skipped_full": 0,
            "tasks_skipped_no_eligible": 0,
            "tasks_skipped_duplicate": 0,
            "tasks_skipped_overloaded": 0,
            "tasks_under_assigned": 0,
            "created_assignments": [],
        }

        with transaction.atomic():
            tasks = list(self.fetch_assignable_tasks().select_for_update())
            if not tasks:
                logger.info("NLP task assignment found no assignable tasks")
                return summary

            annotator_state = self._build_annotator_state(self.fetch_eligible_annotators().select_for_update())

            for task in tasks:
                summary["tasks_scanned"] += 1

                current_count = self.calculate_task_assignment_count(task)
                missing_slots = self.TARGET_ANNOTATORS_PER_TASK - current_count

                if missing_slots <= 0:
                    summary["tasks_skipped_full"] += 1
                    logger.info("Skipping fully assigned NLP task id=%s", task.pk)
                    continue

                selected_annotators = self.select_best_annotators(
                    task=task,
                    annotator_state=annotator_state,
                    limit=missing_slots,
                )

                if not selected_annotators:
                    summary["tasks_skipped_no_eligible"] += 1
                    summary["tasks_under_assigned"] += 1
                    logger.info("No eligible annotators found for NLP task id=%s", task.pk)
                    continue

                assignments = self.assign_task(task, selected_annotators)
                created_count = len(assignments)

                if created_count:
                    summary["tasks_assigned"] += 1
                    summary["assignments_created"] += created_count
                    summary["created_assignments"].extend(
                        {
                            "assignment_id": assignment.id,
                            "task_id": assignment.task_id,
                            "annotator_id": assignment.annotator_id,
                        }
                        for assignment in assignments
                    )

                    for assignment in assignments:
                        self._bump_annotator_state(annotator_state, assignment.annotator_id)

                    logger.info(
                        "Assigned NLP task id=%s to annotators=%s",
                        task.pk,
                        [assignment.annotator_id for assignment in assignments],
                    )

                remaining_slots = self.TARGET_ANNOTATORS_PER_TASK - self.calculate_task_assignment_count(task)
                if remaining_slots > 0:
                    summary["tasks_under_assigned"] += 1
                    logger.info(
                        "NLP task id=%s remains under-assigned with %s remaining slots",
                        task.pk,
                        remaining_slots,
                    )

        logger.info(
            "NLP task assignment completed: tasks_scanned=%s assignments_created=%s tasks_under_assigned=%s",
            summary["tasks_scanned"],
            summary["assignments_created"],
            summary["tasks_under_assigned"],
        )
        return summary

    def fetch_assignable_tasks(self):
        """Return tasks with fewer than three active assignment slots filled."""
        return (
            NLPAnnotationTask.objects.annotate(
                active_assignment_count=Count(
                    "assignments",
                    filter=Q(assignments__status__in=self.TASK_FILL_STATUSES),
                    distinct=True,
                )
            )
            .filter(is_active=True, active_assignment_count__lt=self.TARGET_ANNOTATORS_PER_TASK)
            .order_by("active_assignment_count", "created_at", "pk")
        )

    def fetch_eligible_annotators(self, task: Optional[NLPAnnotationTask] = None):
        """Return annotators who can receive NLP task assignments.

        The current implementation allows all verified annotators. The method
        is structured so future task-type specialization can be added without
        changing the assignment loop.
        """
        duplicate_subquery = (
            NLPTaskAssignment.objects.filter(task=task, annotator=OuterRef("pk")) if task else None
        )

        queryset = (
            CustomUser.objects.filter(
                is_active=True,
                is_verified=True,
                role=RoleChoices.ANNOTATOR,
            )
            .annotate(
                active_assignment_count=Count(
                    "nlp_task_assignments",
                    filter=Q(nlp_task_assignments__status__in=self.ACTIVE_ASSIGNMENT_STATUSES),
                    distinct=True,
                ),
                last_assignment_at=Coalesce(
                    Max("nlp_task_assignments__assigned_at"),
                    Value(self.OLDEST_LAST_ASSIGNMENT_AT, output_field=DateTimeField()),
                ),
            )
            .filter(active_assignment_count__lt=self.MAX_ACTIVE_ASSIGNMENTS_PER_ANNOTATOR)
        )

        if duplicate_subquery is not None:
            queryset = queryset.annotate(already_assigned=Exists(duplicate_subquery)).filter(already_assigned=False)

        return queryset.order_by("active_assignment_count", "last_assignment_at", "pk")

    def calculate_active_workload(self, annotator: CustomUser) -> int:
        """Count active assignments currently occupying the annotator."""
        return NLPTaskAssignment.objects.filter(
            annotator=annotator,
            status__in=self.ACTIVE_ASSIGNMENT_STATUSES,
        ).count()

    def calculate_task_assignment_count(self, task: NLPAnnotationTask) -> int:
        """Count task slots that are already occupied."""
        return NLPTaskAssignment.objects.filter(task=task, status__in=self.TASK_FILL_STATUSES).count()

    def select_best_annotators(
        self,
        task: NLPAnnotationTask,
        annotator_state: Dict[int, Dict[str, object]],
        limit: int,
    ) -> List[CustomUser]:
        """Select annotators with the smallest active workload for a task."""
        assigned_ids = set(
            NLPTaskAssignment.objects.filter(task=task).values_list("annotator_id", flat=True)
        )

        candidates = [
            state
            for state in annotator_state.values()
            if state["annotator"].pk not in assigned_ids
            and state["active_assignment_count"] < self.MAX_ACTIVE_ASSIGNMENTS_PER_ANNOTATOR
            and self._annotator_supports_task_type(state["annotator"], task)
        ]

        candidates.sort(
            key=lambda state: (
                state["active_assignment_count"],
                state["last_assignment_at"],
                state["annotator"].pk,
            )
        )

        selected = [state["annotator"] for state in candidates[:limit]]

        if selected:
            logger.info(
                "Selected annotators for task id=%s with workloads=%s",
                task.pk,
                [
                    {
                        "annotator_id": annotator.pk,
                        "workload": annotator_state[annotator.pk]["active_assignment_count"],
                    }
                    for annotator in selected
                ],
            )

        return selected

    def assign_task(self, task: NLPAnnotationTask, annotators: Sequence[CustomUser]) -> List[NLPTaskAssignment]:
        """Create assignment rows for a task and the selected annotators."""
        if not annotators:
            return []

        existing_annotator_ids = set(
            NLPTaskAssignment.objects.filter(task=task, annotator__in=annotators).values_list("annotator_id", flat=True)
        )

        assignments = [
            NLPTaskAssignment(
                task=task,
                annotator=annotator,
                status=NLPTaskAssignmentStatusChoices.ASSIGNED,
            )
            for annotator in annotators
            if annotator.pk not in existing_annotator_ids
        ]

        if not assignments:
            return []

        try:
            NLPTaskAssignment.objects.bulk_create(assignments)
        except IntegrityError:
            # Re-read rows if a concurrent writer created some of them first.
            assignments = list(
                NLPTaskAssignment.objects.filter(task=task, annotator__in=annotators)
            )

        return assignments

    def _build_annotator_state(self, annotators: Iterable[CustomUser]) -> Dict[int, Dict[str, object]]:
        """Build an in-memory workload cache for fair assignment ordering."""
        state: Dict[int, Dict[str, object]] = {}
        for annotator in annotators:
            state[annotator.pk] = {
                "annotator": annotator,
                "active_assignment_count": getattr(annotator, "active_assignment_count", None)
                if getattr(annotator, "active_assignment_count", None) is not None
                else self.calculate_active_workload(annotator),
                "last_assignment_at": getattr(annotator, "last_assignment_at", self.OLDEST_LAST_ASSIGNMENT_AT),
            }
        return state

    def _bump_annotator_state(self, annotator_state: Dict[int, Dict[str, object]], annotator_id: int) -> None:
        """Increment the cached workload after creating an assignment."""
        state = annotator_state.get(annotator_id)
        if not state:
            return
        state["active_assignment_count"] = int(state["active_assignment_count"]) + 1
        state["last_assignment_at"] = timezone.now()

    def _annotator_supports_task_type(self, annotator: CustomUser, task: NLPAnnotationTask) -> bool:
        """Future specialization hook.

        Right now all verified annotators can take any NLP task type. This hook
        exists so task-type preferences can be added later without rewriting the
        assignment flow.
        """
        _ = annotator
        _ = task
        return True


__all__ = ["NLPTaskAssignmentService"]