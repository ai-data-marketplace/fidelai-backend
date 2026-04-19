from django.urls import path

from apps.users.views import (
	ForgotPasswordView,
	LoginView,
	RegisterView,
	ResendCodeView,
	ResetPasswordView,
	VerifyEmailView,
)

urlpatterns = [
	path("register/", RegisterView.as_view(), name="auth-register"),
	path("verify-email/", VerifyEmailView.as_view(), name="auth-verify-email"),
	path("resend-code/", ResendCodeView.as_view(), name="auth-resend-code"),
	path("login/", LoginView.as_view(), name="auth-login"),
	path("forgot-password/", ForgotPasswordView.as_view(), name="auth-forgot-password"),
	path("reset-password/", ResetPasswordView.as_view(), name="auth-reset-password"),
]
