import json
import logging
from datetime import datetime, timezone as datetime_timezone

from django.db import transaction
from django.db.models import Count, Max, Q, Value, DateTimeField
from django.db.models.functions import Coalesce

from apps.notifications.services import notify_adjudication_required
from apps.processing.models.expert_review import ExpertTask, ExpertTaskAssignment
from apps.processing.models.chunk import TaskAssignmentStatusChoices
from apps.users.models import CustomUser, RoleApplicationStatusChoices, RoleChoices

logger = logging.getLogger(__name__)


class ExpertTaskAssignmentService:
    MAX_ACTIVE_EXPERT_TASKS = 10
    ACTIVE_STATUSES = (
        TaskAssignmentStatusChoices.ASSIGNED,
        TaskAssignmentStatusChoices.ACCEPTED,
        TaskAssignmentStatusChoices.IN_PROGRESS,
    )
    OLDEST_IDLE_AT = datetime(1970, 1, 1, tzinfo=datetime_timezone.utc)

    def assign_expert_tasks(self, batch_size: int = 50):
        summary = {
            "tasks_scanned": 0,
            "experts_matched": 0,
            "assignments_created": 0,
            "tasks_skipped": 0,
            "overloaded_experts": 0,
            "no_domain_match_failures": 0,
            "errors": 0,
        }

        tasks = list(self.get_pending_expert_tasks()[:batch_size])
        summary["tasks_scanned"] = len(tasks)

        for task in tasks:
            try:
                experts = self.get_available_experts_for_domain(task.domain)
                if not experts:
                    summary["no_domain_match_failures"] += 1
                    summary["tasks_skipped"] += 1
                    logger.info("No eligible experts found for ExpertTask %s domain=%s", task.id, task.domain)
                    continue

                summary["experts_matched"] += len(experts)
                expert = self.select_best_expert(experts)
                if not expert:
                    summary["tasks_skipped"] += 1
                    continue

                with transaction.atomic():
                    locked_task = ExpertTask.objects.select_for_update().get(pk=task.pk)
                    existing_assignment = locked_task.expert_assignments.first()

                    if existing_assignment and existing_assignment.status in self.ACTIVE_STATUSES:
                        summary["tasks_skipped"] += 1
                        continue

                    active_load = self.calculate_expert_active_load(expert)
                    if active_load >= self.MAX_ACTIVE_EXPERT_TASKS:
                        summary["overloaded_experts"] += 1
                        summary["tasks_skipped"] += 1
                        continue

                    assignment = existing_assignment
                    if assignment:
                        assignment.expert = expert
                        assignment.status = TaskAssignmentStatusChoices.ASSIGNED
                        assignment.started_at = None
                        assignment.completed_at = None
                        assignment.save(update_fields=["expert", "status", "started_at", "completed_at"])
                    else:
                        assignment = ExpertTaskAssignment.objects.create(
                            expert_task=locked_task,
                            expert=expert,
                            status=TaskAssignmentStatusChoices.ASSIGNED,
                        )

                    first_chunk = locked_task.task_chunks.select_related("chunk").order_by("chunk__order_index").first()
                    if first_chunk:
                        try:
                            notify_adjudication_required(user=expert, chunk_id=first_chunk.chunk_id)
                        except ValueError:
                            logger.warning(
                                "Notification template missing for adjudication task=%s expert=%s chunk=%s",
                                locked_task.pk,
                                expert.pk,
                                first_chunk.chunk_id,
                            )

                summary["assignments_created"] += 1
                logger.info(
                    "Assigned ExpertTask %s to expert %s",
                    task.id,
                    expert.id,
                )
            except Exception:
                summary["errors"] += 1
                logger.exception("Failed assigning ExpertTask %s", task.id)

        logger.info(
            "Expert task assignment complete: tasks_scanned=%s experts_matched=%s assignments_created=%s tasks_skipped=%s overloaded_experts=%s no_domain_match_failures=%s errors=%s",
            summary["tasks_scanned"],
            summary["experts_matched"],
            summary["assignments_created"],
            summary["tasks_skipped"],
            summary["overloaded_experts"],
            summary["no_domain_match_failures"],
            summary["errors"],
        )
        return summary

    def get_pending_expert_tasks(self):
        return (
            ExpertTask.objects.select_related()
            .prefetch_related("expert_assignments")
            .filter(Q(expert_assignments__isnull=True) | Q(expert_assignments__status=TaskAssignmentStatusChoices.DECLINED))
            .distinct()
            .order_by("created_at")
        )

    def calculate_expert_active_load(self, expert):
        return ExpertTaskAssignment.objects.filter(
            expert=expert,
            status__in=self.ACTIVE_STATUSES,
        ).count()

    def get_available_experts_for_domain(self, domain):
        experts = (
            CustomUser.objects.filter(
                is_active=True,
                is_verified=True,
                role=RoleChoices.EXPERT,
            )
            .annotate(
                active_task_count=Count(
                    "expert_task_assignments",
                    filter=Q(expert_task_assignments__status__in=self.ACTIVE_STATUSES),
                    distinct=True,
                ),
                performance_points=Coalesce(
                    Max("user_score__total_points"),
                    Value(0),
                ),
                last_assigned_at=Coalesce(
                    Max("expert_task_assignments__assigned_at"),
                    Value(self.OLDEST_IDLE_AT, output_field=DateTimeField()),
                ),
            )
            .filter(active_task_count__lt=self.MAX_ACTIVE_EXPERT_TASKS)
            .select_related("user_score")
            .prefetch_related("role_applications")
            .order_by("active_task_count", "-performance_points", "last_assigned_at", "pk")
        )

        matching_experts = []
        for expert in experts:
            if self._expert_matches_domain(expert, domain):
                matching_experts.append(expert)

        return matching_experts

    def _expert_matches_domain(self, expert, domain):
        applications = expert.role_applications.filter(role_applied_for=RoleChoices.EXPERT).order_by("-submitted_at")
        application = applications.filter(status=RoleApplicationStatusChoices.APPROVED).first() or applications.first()
        if not application:
            return False

        specialization = application.application_data.get("step_2", {}).get("domain_specialization")
        return domain in self._normalize_domain_specialization(specialization)

    def _normalize_domain_specialization(self, specialization):
        if specialization is None:
            return []
        if isinstance(specialization, str):
            try:
                parsed = json.loads(specialization)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
                if isinstance(parsed, dict):
                    return [str(value) for value in parsed.values()]
            except json.JSONDecodeError:
                return [specialization]
            return [str(parsed)]
        if isinstance(specialization, dict):
            return [str(value) for value in specialization.values()]
        if isinstance(specialization, (list, tuple, set)):
            return [str(item) for item in specialization]
        return [str(specialization)]

    def select_best_expert(self, experts):
        if not experts:
            return None
        return experts[0]
