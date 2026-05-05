from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import CustomUser, RoleApplication, RoleApplicationStatusChoices, RoleChoices


class RoleManagementAPITests(APITestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com",
            username="admin",
            full_name="Admin User",
            password="password123",
            role=RoleChoices.ADMIN,
            is_verified=True,
        )
        self.annotator = CustomUser.objects.create_user(
            email="annotator@example.com",
            username="annotator",
            full_name="Annotator User",
            password="password123",
            role=RoleChoices.UNKNOWN,
            is_verified=True,
        )
        self.expert = CustomUser.objects.create_user(
            email="expert@example.com",
            username="expert",
            full_name="Expert User",
            password="password123",
            role=RoleChoices.UNKNOWN,
            is_verified=True,
        )

        self.pending_application = RoleApplication.objects.create(
            user=self.annotator,
            role_applied_for=RoleChoices.ANNOTATOR,
            application_data={"step_2": {"preferred_domains": ["other"]}},
            status=RoleApplicationStatusChoices.PENDING,
        )
        self.approved_application = RoleApplication.objects.create(
            user=self.expert,
            role_applied_for=RoleChoices.EXPERT,
            application_data={"step_2": {"domain_specialization": ["other"]}},
            status=RoleApplicationStatusChoices.APPROVED,
        )

    def test_admin_can_list_users(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/auth/admin/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        first_row = response.data["results"][0]
        self.assertIn("user", first_row)
        self.assertIn("role", first_row)
        self.assertIn("status", first_row)
        self.assertIn("verification", first_row)
        self.assertIn("joined_date", first_row)

    def test_non_admin_cannot_list_users(self):
        self.client.force_authenticate(user=self.annotator)

        response = self.client.get("/api/auth/admin/users/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_list_returns_only_pending_applications(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/auth/admin/role-applications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.pending_application.id))

    def test_admin_can_approve_role_application(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(f"/api/auth/admin/role-applications/{self.pending_application.id}/approve/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.pending_application.refresh_from_db()
        self.annotator.refresh_from_db()

        self.assertEqual(self.pending_application.status, RoleApplicationStatusChoices.APPROVED)
        self.assertEqual(self.pending_application.reviewed_by_id, self.admin.id)
        self.assertIsNotNone(self.pending_application.reviewed_at)
        self.assertEqual(self.annotator.role, RoleChoices.ANNOTATOR)

    def test_admin_can_reject_role_application(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(f"/api/auth/admin/role-applications/{self.approved_application.id}/reject/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.approved_application.refresh_from_db()
        self.assertEqual(self.approved_application.status, RoleApplicationStatusChoices.APPROVED)

        new_application = RoleApplication.objects.create(
            user=self.annotator,
            role_applied_for=RoleChoices.EXPERT,
            application_data={"step_2": {"domain_specialization": ["other"]}},
            status=RoleApplicationStatusChoices.PENDING,
        )

        response = self.client.post(f"/api/auth/admin/role-applications/{new_application.id}/reject/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_application.refresh_from_db()
        self.assertEqual(new_application.status, RoleApplicationStatusChoices.REJECTED)
        self.assertEqual(new_application.reviewed_by_id, self.admin.id)
        self.assertIsNotNone(new_application.reviewed_at)

    def test_non_admin_cannot_access_role_management(self):
        self.client.force_authenticate(user=self.annotator)

        response = self.client.get("/api/auth/admin/role-applications/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)