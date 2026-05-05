from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.notifications.models import NotificationTemplate, NotificationTypeChoices
from apps.processing.models import AnnotationTask, TaskAssignment, TaskAssignmentStatusChoices
from apps.processing.services import TaskAssignmentService
from apps.users.models import CustomUser, RoleChoices


class TaskAssignmentServiceTests(TestCase):
    def setUp(self):
        self.service = TaskAssignmentService()
        NotificationTemplate.objects.create(
            notification_type=NotificationTypeChoices.TASK_ASSIGNED,
            category="tasks",
            title_template="Assigned: {task_name}",
            message_template="Task {task_name} has been assigned.",
            active=True,
        )

    def create_annotator(self, email, *, is_verified=True, is_active=True):
        return CustomUser.objects.create_user(
            email=email,
            username=email.split("@")[0],
            full_name="Annotator User",
            password="test-password",
            role=RoleChoices.ANNOTATOR,
            is_verified=is_verified,
            is_active=is_active,
        )

    def create_task(self, name="Task", domain="other"):
        return AnnotationTask.objects.create(name=name, domain=domain)

    def test_create_assignment_prevents_duplicates(self):
        annotator = self.create_annotator("annotator1@example.com")
        task = self.create_task()
        existing_assignment = TaskAssignment.objects.create(task=task, annotator=annotator)

        assignment, created, reason = self.service.create_assignment(task, annotator)

        self.assertFalse(created)
        self.assertEqual(reason, "duplicate")
        self.assertEqual(assignment.pk, existing_assignment.pk)
        self.assertEqual(TaskAssignment.objects.filter(task=task, annotator=annotator).count(), 1)

    def test_assign_pending_tasks_skips_overloaded_annotators(self):
        overloaded = self.create_annotator("overloaded@example.com")
        available_one = self.create_annotator("available1@example.com")
        available_two = self.create_annotator("available2@example.com")
        filler_one = self.create_annotator("filler1@example.com", is_active=False)
        filler_two = self.create_annotator("filler2@example.com", is_verified=False)
        task = self.create_task(name="Overload task")

        for index in range(self.service.MAX_PENDING_ASSIGNMENTS):
            other_task = self.create_task(name=f"Workload task {index}")
            TaskAssignment.objects.create(
                task=other_task,
                annotator=overloaded,
                status=TaskAssignmentStatusChoices.ASSIGNED,
            )
            TaskAssignment.objects.create(
                task=other_task,
                annotator=filler_one,
                status=TaskAssignmentStatusChoices.ACCEPTED,
            )
            TaskAssignment.objects.create(
                task=other_task,
                annotator=filler_two,
                status=TaskAssignmentStatusChoices.IN_PROGRESS,
            )

        with transaction.atomic():
            eligible_ids = list(self.service.get_eligible_annotators(task).values_list("id", flat=True))

        self.assertNotIn(overloaded.id, eligible_ids)
        self.assertIn(available_one.id, eligible_ids)
        self.assertIn(available_two.id, eligible_ids)

        result = self.service.assign_pending_tasks()

        assigned_annotator_ids = set(TaskAssignment.objects.filter(task=task).values_list("annotator_id", flat=True))
        self.assertNotIn(overloaded.id, assigned_annotator_ids)
        self.assertSetEqual(assigned_annotator_ids, {available_one.id, available_two.id})
        self.assertEqual(result["assignments_created"], 2)

    def test_assign_pending_tasks_fills_multi_annotator_consensus(self):
        annotators = [
            self.create_annotator("annotator-a@example.com"),
            self.create_annotator("annotator-b@example.com"),
            self.create_annotator("annotator-c@example.com"),
        ]
        task = self.create_task(name="Consensus task")

        result = self.service.assign_pending_tasks()

        assignments = list(TaskAssignment.objects.filter(task=task).order_by("annotator_id"))
        self.assertEqual(len(assignments), self.service.TARGET_ANNOTATORS_PER_TASK)
        self.assertSetEqual({assignment.annotator_id for assignment in assignments}, {user.id for user in annotators})
        self.assertTrue(all(assignment.status == TaskAssignmentStatusChoices.ASSIGNED for assignment in assignments))
        self.assertEqual(result["assignments_created"], self.service.TARGET_ANNOTATORS_PER_TASK)

    def test_create_assignment_recovers_from_race_condition_collision(self):
        annotator = self.create_annotator("race@example.com")
        task = self.create_task(name="Race task")
        existing_assignment = TaskAssignment.objects.create(task=task, annotator=annotator)

        class FakeQuerySet:
            def exists(self):
                return False

            def first(self):
                return existing_assignment

        with transaction.atomic():
            original_filter = TaskAssignment.objects.filter

            def filter_side_effect(*args, **kwargs):
                if kwargs.get("task") == task and kwargs.get("annotator") == annotator:
                    return FakeQuerySet()
                return original_filter(*args, **kwargs)

            with patch.object(self.service, "get_annotator_workload", return_value=0), patch.object(
                TaskAssignment.objects,
                "filter",
                side_effect=filter_side_effect,
            ), patch.object(
                TaskAssignment.objects,
                "create",
                side_effect=IntegrityError("duplicate key value violates unique constraint"),
            ):
                assignment, created, reason = self.service.create_assignment(task, annotator)

        self.assertFalse(created)
        self.assertEqual(reason, "duplicate")
        self.assertEqual(assignment.pk, existing_assignment.pk)
        self.assertEqual(TaskAssignment.objects.filter(task=task, annotator=annotator).count(), 1)

    def test_declined_assignment_frees_slot_for_reassignment(self):
        a1 = self.create_annotator("d1@example.com")
        a2 = self.create_annotator("d2@example.com")
        a3 = self.create_annotator("d3@example.com")
        a4 = self.create_annotator("d4@example.com")
        task = self.create_task(name="Decline frees slot")

        # Two active, one declined -> should free one slot
        TaskAssignment.objects.create(task=task, annotator=a1, status=TaskAssignmentStatusChoices.ASSIGNED)
        TaskAssignment.objects.create(task=task, annotator=a2, status=TaskAssignmentStatusChoices.ASSIGNED)
        TaskAssignment.objects.create(task=task, annotator=a3, status=TaskAssignmentStatusChoices.DECLINED)

        result = self.service.assign_pending_tasks()

        assignments = TaskAssignment.objects.filter(task=task)
        # Declined row remains; a new assignment should be created for a4
        self.assertEqual(assignments.count(), 4)
        # Ensure three non-declined assignments exist (a1,a2 and the new one)
        non_declined = assignments.exclude(status=TaskAssignmentStatusChoices.DECLINED)
        self.assertEqual(non_declined.count(), 3)

    def test_submitted_assignment_blocks_slot_from_reassignment(self):
        s1 = self.create_annotator("s1@example.com")
        s2 = self.create_annotator("s2@example.com")
        s3 = self.create_annotator("s3@example.com")
        task = self.create_task(name="Submitted blocks slot")

        # Two active, one submitted -> submitted should count as filling the slot
        TaskAssignment.objects.create(task=task, annotator=s1, status=TaskAssignmentStatusChoices.ASSIGNED)
        TaskAssignment.objects.create(task=task, annotator=s2, status=TaskAssignmentStatusChoices.ASSIGNED)
        TaskAssignment.objects.create(task=task, annotator=s3, status=TaskAssignmentStatusChoices.SUBMITTED)

        result = self.service.assign_pending_tasks()

        assignments = TaskAssignment.objects.filter(task=task)
        # No extra assignment should be created because submitted counts as filled
        self.assertEqual(assignments.count(), 3)