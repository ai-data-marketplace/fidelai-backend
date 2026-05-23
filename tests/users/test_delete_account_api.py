from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import CustomUser, RoleChoices
from core.services.auth_service import AuthService


class DeleteAccountAPITests(APITestCase):
    def setUp(self):
        self.password = "Password123!"
        self.user = CustomUser.objects.create_user(
            email="delete-me@example.com",
            username="delete_me",
            full_name="Delete Me",
            password=self.password,
            role=RoleChoices.BUYER,
            is_verified=True,
        )

    def test_delete_account_requires_authentication(self):
        response = self.client.post(
            "/api/auth/delete-account/",
            {"password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_account_success(self):
        user_id = self.user.id
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/auth/delete-account/",
            {"password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Account deleted successfully")

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.is_verified)
        self.assertEqual(self.user.email, f"deleted.{user_id}@deleted.local")
        self.assertEqual(self.user.username, f"deleted_{user_id}")
        self.assertEqual(self.user.full_name, "Deleted User")
        self.assertFalse(self.user.has_usable_password())
        self.assertTrue(AuthService._is_account_deleted(self.user))

    def test_delete_account_rejects_incorrect_password(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/auth/delete-account/",
            {"password": "WrongPassword123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "Password is incorrect.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "delete-me@example.com")
        self.assertTrue(self.user.is_active)

    def test_delete_account_is_idempotent_guard(self):
        self.client.force_authenticate(user=self.user)

        first = self.client.post(
            "/api/auth/delete-account/",
            {"password": self.password},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self.client.post(
            "/api/auth/delete-account/",
            {"password": self.password},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second.data["message"], "This account has already been deleted.")

    def test_delete_account_blocks_staff_users(self):
        staff_user = CustomUser.objects.create_user(
            email="staff@example.com",
            username="staff_user",
            full_name="Staff User",
            password=self.password,
            role=RoleChoices.ADMIN,
            is_verified=True,
            is_staff=True,
        )
        self.client.force_authenticate(user=staff_user)

        response = self.client.post(
            "/api/auth/delete-account/",
            {"password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Staff accounts", response.data["message"])
        staff_user.refresh_from_db()
        self.assertEqual(staff_user.email, "staff@example.com")
