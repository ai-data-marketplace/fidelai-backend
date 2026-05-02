import logging
from datetime import datetime, timezone

from django.db import IntegrityError, transaction
from django.db.models import Count, DateTimeField, Exists, Max, OuterRef, Q, Value
from django.db.models.functions import Coalesce

from apps.processing.models import AnnotationTask, TaskAssignment, TaskAssignmentStatusChoices
from apps.users.models import CustomUser, RoleChoices


logger = logging.getLogger(__name__)


class TaskAssignmentService:
    TARGET_ANNOTATORS_PER_TASK = 3
    MAX_PENDING_ASSIGNMENTS = 10
    ACTIVE_ASSIGNMENT_STATUSES = (
        TaskAssignmentStatusChoices.ASSIGNED,
        TaskAssignmentStatusChoices.ACCEPTED,
        TaskAssignmentStatusChoices.IN_PROGRESS,
    )
    OLDEST_LAST_ASSIGNMENT_AT = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def assign_pending_tasks(self):
        """Assign unfilled tasks to eligible annotators.

        The work happens in a transaction so overlapping scheduler runs do not
        assign the same task or annotator twice.
        """

        summary = {
            "tasks_scanned": 0,
            "tasks_assigned": 0,
            "assignments_created": 0,
            "tasks_skipped_full": 0,
            "tasks_skipped_no_eligible": 0,
            "tasks_skipped_duplicate": 0,
            "tasks_skipped_overloaded": 0,
        }

        with transaction.atomic():
            tasks = list(self.get_unfilled_tasks().select_for_update())

            for task in tasks:
                summary["tasks_scanned"] += 1
                current_count = self.get_current_assignment_count(task)
                missing_slots = self.TARGET_ANNOTATORS_PER_TASK - current_count

                if missing_slots <= 0:
                    summary["tasks_skipped_full"] += 1
                    continue

                eligible_annotators = list(self.get_eligible_annotators(task)[:missing_slots])
                if not eligible_annotators:
                    summary["tasks_skipped_no_eligible"] += 1
                    logger.info("No eligible annotators for task %s", task.pk)
                    continue

                created_for_task = 0
                for annotator in eligible_annotators:
                    assignment, created, reason = self.create_assignment(task, annotator)
                    if created:
                        created_for_task += 1
                        summary["assignments_created"] += 1
                        logger.info(
                            "Created task assignment task=%s annotator=%s",
                            task.pk,
                            annotator.pk,
                        )
                        continue

                    if reason == "duplicate":
                        summary["tasks_skipped_duplicate"] += 1
                    elif reason == "overloaded":
                        summary["tasks_skipped_overloaded"] += 1

                    logger.info(
                        "Skipped task assignment task=%s annotator=%s reason=%s",
                        task.pk,
                        annotator.pk,
                        reason,
                    )

                if created_for_task:
                    summary["tasks_assigned"] += 1

        return summary

    def get_unfilled_tasks(self):
        # Count assignments that should be considered filling a task slot.
        # `DECLINED` should free a slot so we exclude it; `SUBMITTED` should
        # still count as filling the slot (annotator completed work).
        active_statuses_for_task_fill = [
            TaskAssignmentStatusChoices.ASSIGNED,
            TaskAssignmentStatusChoices.ACCEPTED,
            TaskAssignmentStatusChoices.IN_PROGRESS,
            TaskAssignmentStatusChoices.SUBMITTED,
        ]

        return (
            AnnotationTask.objects.annotate(
                active_assignment_count=Count(
                    "assignments",
                    filter=Q(assignments__status__in=active_statuses_for_task_fill),
                    distinct=True,
                ),
            )
            .filter(active_assignment_count__lt=self.TARGET_ANNOTATORS_PER_TASK)
            .order_by("active_assignment_count", "created_at", "pk")
        )

    def get_current_assignment_count(self, task):
        # Count assignments that should be considered filling a task slot.
        active_statuses_for_task_fill = [
            TaskAssignmentStatusChoices.ASSIGNED,
            TaskAssignmentStatusChoices.ACCEPTED,
            TaskAssignmentStatusChoices.IN_PROGRESS,
            TaskAssignmentStatusChoices.SUBMITTED,
        ]
        return TaskAssignment.objects.filter(task=task, status__in=active_statuses_for_task_fill).count()

    def get_eligible_annotators(self, task):
        duplicate_subquery = TaskAssignment.objects.filter(task=task, annotator=OuterRef("pk"))

        return (
            CustomUser.objects.filter(
                is_active=True,
                is_verified=True,
                role=RoleChoices.ANNOTATOR,
            )
            .annotate(
                active_assignment_count=Count(
                    "task_assignments",
                    filter=Q(task_assignments__status__in=self.ACTIVE_ASSIGNMENT_STATUSES),
                    distinct=True,
                ),
                last_assignment_at=Coalesce(
                    Max("task_assignments__assigned_at"),
                    Value(self.OLDEST_LAST_ASSIGNMENT_AT, output_field=DateTimeField()),
                ),
                already_assigned=Exists(duplicate_subquery),
            )
            .filter(
                active_assignment_count__lt=self.MAX_PENDING_ASSIGNMENTS,
                already_assigned=False,
            )
            .select_for_update()
            .order_by("active_assignment_count", "last_assignment_at", "pk")
        )

    def get_annotator_workload(self, annotator):
        return TaskAssignment.objects.filter(
            annotator=annotator,
            status__in=self.ACTIVE_ASSIGNMENT_STATUSES,
        ).count()

    def create_assignment(self, task, annotator):
        if TaskAssignment.objects.filter(task=task, annotator=annotator).exists():
            return TaskAssignment.objects.filter(task=task, annotator=annotator).first(), False, "duplicate"

        if self.get_annotator_workload(annotator) >= self.MAX_PENDING_ASSIGNMENTS:
            return None, False, "overloaded"

        try:
            with transaction.atomic():
                assignment = TaskAssignment.objects.create(
                    task=task,
                    annotator=annotator,
                    status=TaskAssignmentStatusChoices.ASSIGNED,
                )
            return assignment, True, None
        except IntegrityError:
            assignment = TaskAssignment.objects.filter(task=task, annotator=annotator).first()
            return assignment, False, "duplicate"