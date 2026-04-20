from django.urls import path

from apps.users.views import (
	ForgotPasswordView,
	LoginView,
	MeView,
	RegisterView,
	ResendCodeView,
	ResetPasswordView,
	VerifyEmailView,
)
from apps.users.views.onboarding import OnboardingView

from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

urlpatterns = [
	path("register/", RegisterView.as_view(), name="auth-register"),
	path("verify-email/", VerifyEmailView.as_view(), name="auth-verify-email"),
	path("resend-code/", ResendCodeView.as_view(), name="auth-resend-code"),
	path("login/", LoginView.as_view(), name="auth-login"),
	path("me/", MeView.as_view(), name="auth-me"),
	path("onboarding/complete/", OnboardingView.as_view(), name="onboarding-complete"),
	path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
	path("token/verify/", TokenVerifyView.as_view(), name="token-verify"),
	path("forgot-password/", ForgotPasswordView.as_view(), name="auth-forgot-password"),
	path("reset-password/", ResetPasswordView.as_view(), name="auth-reset-password"),
]
