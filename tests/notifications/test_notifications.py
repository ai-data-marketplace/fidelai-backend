from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification, NotificationTemplate, NotificationTypeChoices
from apps.notifications.services import send_notification
from apps.processing.models import AnnotationTask, TaskAssignment
from apps.processing.services import TaskAssignmentService
from apps.users.models import CustomUser, RoleChoices


class NotificationTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="user@example.com",
            username="user",
            full_name="Test User",
            password="password123",
            role=RoleChoices.ANNOTATOR,
            is_verified=True,
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@example.com",
            username="other",
            full_name="Other User",
            password="password123",
            role=RoleChoices.ANNOTATOR,
            is_verified=True,
        )
        self.task = AnnotationTask.objects.create(name="Task A", domain="other")
        self.create_template(
            NotificationTypeChoices.TASK_ASSIGNED,
            category="tasks",
            title_template="Assigned: {task_name}",
            message_template="Task {task_name} has been assigned.",
        )
        self.create_template(
            NotificationTypeChoices.TASK_COMPLETED,
            category="tasks",
            title_template="Completed: {task_name}",
            message_template="Task {task_name} was completed.",
        )
        self.create_template(
            NotificationTypeChoices.ADJUDICATION_REQUIRED,
            category="system",
            title_template="Review required for chunk {chunk_id}",
            message_template="Chunk {chunk_id} needs adjudication.",
        )
        self.create_template(
            NotificationTypeChoices.TASK_REVIEWED,
            category="system",
            title_template="Reviewed chunk {chunk_id}",
            message_template="Chunk {chunk_id} has been reviewed.",
        )

    def create_template(self, notification_type, *, category, title_template, message_template):
        return NotificationTemplate.objects.create(
            notification_type=notification_type,
            category=category,
            title_template=title_template,
            message_template=message_template,
            active=True,
        )

    def test_send_notification_renders_and_deduplicates(self):
        notification = send_notification(
            user=self.user,
            notification_type=NotificationTypeChoices.TASK_ASSIGNED,
            context={"task_name": self.task.name},
            related_task=self.task,
        )

        self.assertIsNotNone(notification)
        self.assertEqual(notification.title, "Assigned: Task A")
        self.assertEqual(notification.message, "Task Task A has been assigned.")
        self.assertEqual(Notification.objects.count(), 1)

        duplicate = send_notification(
            user=self.user,
            notification_type=NotificationTypeChoices.TASK_ASSIGNED,
            context={"task_name": self.task.name},
            related_task=self.task,
        )
        self.assertIsNone(duplicate)
        self.assertEqual(Notification.objects.count(), 1)

    def test_task_assignment_service_creates_notification(self):
        service = TaskAssignmentService()

        assignment, created, reason = service.create_assignment(self.task, self.user)

        self.assertTrue(created)
        self.assertIsNone(reason)
        self.assertIsNotNone(assignment)
        self.assertEqual(TaskAssignment.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.user, notification_type=NotificationTypeChoices.TASK_ASSIGNED).count(), 1)

    def test_list_filtering_and_read_state_endpoints(self):
        task_notification = send_notification(
            user=self.user,
            notification_type=NotificationTypeChoices.TASK_ASSIGNED,
            context={"task_name": self.task.name},
            related_task=self.task,
        )
        other_notification = send_notification(
            user=self.user,
            notification_type=NotificationTypeChoices.TASK_COMPLETED,
            context={"task_name": self.task.name},
            related_task=self.task,
            send_email=True,
        )
        send_notification(
            user=self.user,
            notification_type=NotificationTypeChoices.ADJUDICATION_REQUIRED,
            context={"chunk_id": "chunk-1"},
        )
        Notification.objects.create(
            user=self.other_user,
            category="account",
            notification_type=NotificationTypeChoices.ROLE_APPROVED,
            title="Ignore",
            message="Ignore",
        )

        Notification.objects.filter(pk=other_notification.pk).update(is_read=True, read_at=timezone.now())

        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/notifications/?category=tasks")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

        response = self.client.get("/api/notifications/?is_read=false")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

        response = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 2)

        response = self.client.post(f"/api/notifications/{task_notification.id}/read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(response.data["unread_count"], 1)

        response = self.client.post("/api/notifications/read-all/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get("/api/notifications/?is_read=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)