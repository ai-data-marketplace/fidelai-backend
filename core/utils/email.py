from django.conf import settings
from django.core.mail import send_mail


def send_verification_email(user, code):
    subject = "Your verification code"
    message = (
        "Hello,\n\n"
        f"Your verification code is: {code}\n"
        "This code expires in 10 minutes.\n\n"
        "If you did not request this, please ignore this email."
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def send_password_reset_email(user, reset_link):
    subject = "Reset your password"
    message = (
        "Hello,\n\n"
        "Use the link below to reset your password:\n"
        f"{reset_link}\n\n"
        "This link expires automatically based on security policy.\n\n"
        "If you did not request this, please ignore this email."
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def send_notification_email(user, subject: str, message: str):
    """Send a plain-text notification email to the user.

    Thin wrapper around Django's `send_mail` for notifications.
    """
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
