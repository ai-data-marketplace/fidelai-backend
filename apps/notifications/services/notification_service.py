from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from apps.notifications.models import Notification, NotificationTemplate, NotificationTypeChoices


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

    if send_email:
        notification.email_sent = True
        notification.save(update_fields=["email_sent"])

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