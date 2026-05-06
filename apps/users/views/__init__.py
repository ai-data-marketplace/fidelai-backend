from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.serializers import (
	ForgotPasswordSerializer,
	LoginSerializer,
	RegisterSerializer,
	ResendCodeSerializer,
	ResetPasswordSerializer,
	UserSerializer,
	VerifyEmailSerializer,
)
from core.services.auth_service import AuthService, AuthServiceError
from .role_management import (
	ApproveRoleApplicationView,
	AdminUserListView,
	PendingRoleApplicationListView,
	RejectRoleApplicationView,
)
from apps.users.serializers.role_management import ApplicationStatusSerializer
from apps.users.models import RoleApplication, RoleApplicationStatusChoices


class RegisterView(APIView):
	authentication_classes = []
	permission_classes = []

	@extend_schema(request=RegisterSerializer)
	def post(self, request):
		serializer = RegisterSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		try:
			user = AuthService.register(**serializer.validated_data)
		except AuthServiceError as exc:
			return Response({"message": exc.message}, status=exc.status_code)

		return Response(
			{
				"message": "Verification code sent to email",
				"email": user.email,
			},
			status=status.HTTP_201_CREATED,
		)


class VerifyEmailView(APIView):
	authentication_classes = []
	permission_classes = []

	@extend_schema(request=VerifyEmailSerializer)
	def post(self, request):
		serializer = VerifyEmailSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		try:
			user = AuthService.verify_email_code(**serializer.validated_data)
		except AuthServiceError as exc:
			return Response({"message": exc.message}, status=exc.status_code)

		refresh = RefreshToken.for_user(user)
		return Response(
			{
				"message": "Email verified successfully",
				"access": str(refresh.access_token),
				"refresh": str(refresh),
				"user": {
					"id": str(user.id),
					"email": user.email,
					"full_name": user.full_name,
					"role": user.role,
				},
			},
			status=status.HTTP_200_OK,
		)


class ResendCodeView(APIView):
	authentication_classes = []
	permission_classes = []

	@extend_schema(request=ResendCodeSerializer)
	def post(self, request):
		serializer = ResendCodeSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		try:
			AuthService.resend_verification_code(**serializer.validated_data)
		except AuthServiceError as exc:
			return Response({"message": exc.message}, status=exc.status_code)

		return Response({"message": "Verification code sent to email"}, status=status.HTTP_200_OK)


class LoginView(APIView):
	authentication_classes = []
	permission_classes = []

	@extend_schema(request=LoginSerializer)
	def post(self, request):
		serializer = LoginSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		try:
			user = AuthService.login(**serializer.validated_data)
		except AuthServiceError as exc:
			return Response({"message": exc.message}, status=exc.status_code)

		refresh = RefreshToken.for_user(user)
		return Response(
			{
				"access": str(refresh.access_token),
				"refresh": str(refresh),
				"user": {
					"id": str(user.id),
					"email": user.email,
					"full_name": user.full_name,
					"role": user.role,
				},
			},
			status=status.HTTP_200_OK,
		)


class ForgotPasswordView(APIView):
	authentication_classes = []
	permission_classes = []

	@extend_schema(request=ForgotPasswordSerializer)
	def post(self, request):
		serializer = ForgotPasswordSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		# Intentionally does not reveal account existence.
		AuthService.forgot_password(**serializer.validated_data)
		return Response(
			{"message": "A password reset link has been sent."},
			status=status.HTTP_200_OK,
		)


class ResetPasswordView(APIView):
	authentication_classes = []
	permission_classes = []

	@extend_schema(request=ResetPasswordSerializer)
	def post(self, request):
		serializer = ResetPasswordSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		try:
			AuthService.reset_password(**serializer.validated_data)
		except AuthServiceError as exc:
			return Response({"message": exc.message}, status=exc.status_code)

		return Response({"message": "Password reset successful"}, status=status.HTTP_200_OK)


class MeView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(responses={200: UserSerializer})
	def get(self, request):
		serializer = UserSerializer(request.user)
		return Response(serializer.data)


class ApplicationStatusView(APIView):
	"""Return onboarding / role-application status for the authenticated user.

	Response fields:
	- role: user's current role
	- is_verified: whether email is verified
	- has_application: whether a role application exists
	- application_status: one of RoleApplicationStatusChoices or null
	- role_applied_for: role requested in the latest application or null
	- application_id: UUID of latest application or null
	- submitted_at: ISO timestamp of latest application or null
	"""

	permission_classes = [IsAuthenticated]

	@extend_schema(responses={200: ApplicationStatusSerializer})
	def get(self, request):
		user = request.user

		latest_app = (
			RoleApplication.objects.filter(user=user)
			.order_by("-submitted_at")
			.first()
		)

		if latest_app:
			app_data = {
				"application_id": str(latest_app.id),
				"application_status": latest_app.status,
				"role_applied_for": latest_app.role_applied_for,
				"submitted_at": latest_app.submitted_at.isoformat() if latest_app.submitted_at else None,
			}
			has_application = True
		else:
			app_data = {
				"application_id": None,
				"application_status": None,
				"role_applied_for": None,
				"submitted_at": None,
			}
			has_application = False

		data = {
			"role": user.role,
			"is_verified": user.is_verified,
			"has_application": has_application,
		}
		data.update(app_data)

		serializer = ApplicationStatusSerializer(data)
		return Response(serializer.data)
