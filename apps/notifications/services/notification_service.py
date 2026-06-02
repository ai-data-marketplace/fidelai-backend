from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from apps.notifications.models import Notification, NotificationTemplate, NotificationTypeChoices
from core.utils.email import send_notification_email


def _json_safe(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=str)]
    return value


def send_notification(
    *,
    user,
    notification_type,
    context: dict[str, Any] | None = None,
    related_task=None,
    related_dataset=None,
    related_order=None,
    send_email: bool = False,
):
    template = NotificationTemplate.objects.filter(notification_type=notification_type, active=True).first()
    if not template:
        raise ValueError("Active NotificationTemplate not found")

    context = context or {}

    try:
        title = template.title_template.format(**context)
        message = template.message_template.format(**context)
    except KeyError as exc:
        raise ValueError(f"Missing template context key: {str(exc)}") from exc

    metadata = _json_safe(context)

    # load user preferences (minimal shape expected):
    # { "email_notification": bool, "categories": {"account": bool, ...} }
    prefs = getattr(getattr(user, "userprofile", None), "notification_preferences", {}) or {}
    categories_prefs = prefs.get("categories", {})
    # category in template is one of 'system','tasks','marketplace','account'
    category_enabled = categories_prefs.get(template.category, True)
    if not category_enabled:
        return None

    # decide whether email is allowed: either user enabled it or caller explicitly requested
    email_allowed = bool(prefs.get("email_notification", False) or send_email)

    exists = Notification.objects.filter(
        user=user,
        notification_type=notification_type,
        related_task=related_task,
        related_dataset=related_dataset,
        related_order=related_order,
    ).exists()
    if exists:
        return None

    notification = Notification.objects.create(
        user=user,
        category=template.category,
        notification_type=notification_type,
        title=title,
        message=message,
        metadata=metadata,
        related_task=related_task,
        related_dataset=related_dataset,
        related_order=related_order,
        in_app_sent=True,
        email_sent=False,
    )

    # send email if allowed
    if email_allowed:
        try:
            send_notification_email(user, title, message)
            notification.email_sent = True
            notification.save(update_fields=["email_sent"])
        except Exception:
            # don't crash notification creation if email fails; leave email_sent=False
            pass

    return notification


def notify_task_assigned(user, task):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.TASK_ASSIGNED,
        context={"task_name": task.name},
        related_task=task,
    )


def notify_task_completed(user, task):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.TASK_COMPLETED,
        context={"task_name": task.name},
        related_task=task,
    )


def notify_adjudication_required(user, chunk_id):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.ADJUDICATION_REQUIRED,
        context={"chunk_id": chunk_id},
    )


def notify_task_reviewed(user, chunk_id):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.TASK_REVIEWED,
        context={"chunk_id": chunk_id},
    )

# --- Account notifications ---
def notify_account_verified(user):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.ACCOUNT_VERIFIED,
        context={"full_name": user.full_name},
    )

def notify_role_approved(user, role, send_email: bool = False):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.ROLE_APPROVED,
        context={"role": role},
        send_email=send_email,
    )

def notify_role_rejected(user, role, send_email: bool = False):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.ROLE_REJECTED,
        context={"role": role},
        send_email=send_email,
    )

def notify_password_reset(user):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.PASSWORD_RESET,
        context={"full_name": user.full_name},
    )

# --- Marketplace and payout notifications ---
def notify_dataset_purchased(user, dataset):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.DATASET_PURCHASED,
        context={"dataset_title": dataset.title},
        related_dataset=dataset,
    )

def notify_dataset_sold(user, dataset):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.DATASET_SOLD,
        context={"dataset_title": dataset.title},
        related_dataset=dataset,
    )

def notify_payout_processed(user, withdrawal_request):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.PAYOUT_PROCESSED,
        context={"amount": str(withdrawal_request.amount)},
        related_order=None,
    )

def notify_withdrawal_update(user, withdrawal_request):
    return send_notification(
        user=user,
        notification_type=NotificationTypeChoices.WITHDRAWAL_UPDATE,
        context={"amount": str(withdrawal_request.amount), "status": withdrawal_request.status},
        related_order=None,
    )