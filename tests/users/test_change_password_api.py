from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import CustomUser, RoleChoices


class ChangePasswordAPITests(APITestCase):
    def setUp(self):
        self.current_password = "Password123!"
        self.new_password = "NewPassword456!"
        self.user = CustomUser.objects.create_user(
            email="user@example.com",
            username="user",
            full_name="Test User",
            password=self.current_password,
            role=RoleChoices.BUYER,
            is_verified=True,
        )

    def test_change_password_requires_authentication(self):
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": self.current_password,
                "new_password": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_success(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": self.current_password,
                "new_password": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Password changed successfully")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertIsNone(
            authenticate(username=self.user.email, password=self.current_password)
        )
        self.assertIsNotNone(
            authenticate(username=self.user.email, password=self.new_password)
        )

    def test_change_password_rejects_incorrect_current_password(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": "WrongPassword123!",
                "new_password": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "Current password is incorrect.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.current_password))

    def test_change_password_rejects_same_password(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": self.current_password,
                "new_password": self.current_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["message"],
            "New password must be different from the current password.",
        )

    def test_change_password_validates_strength(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": self.current_password,
                "new_password": "weak",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data)
