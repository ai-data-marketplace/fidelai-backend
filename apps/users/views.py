from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.serializers import (
	ForgotPasswordSerializer,
	LoginSerializer,
	RegisterSerializer,
	ResendCodeSerializer,
	ResetPasswordSerializer,
	VerifyEmailSerializer,
)
from core.services.auth_service import AuthService, AuthServiceError


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
			AuthService.verify_email_code(**serializer.validated_data)
		except AuthServiceError as exc:
			return Response({"message": exc.message}, status=exc.status_code)

		return Response({"message": "Email verified successfully"}, status=status.HTTP_200_OK)


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
