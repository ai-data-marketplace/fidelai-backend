from django.db import models


class NotificationCategoryChoices(models.TextChoices):
    SYSTEM = "system", "System"
    TASKS = "tasks", "Tasks"
    MARKETPLACE = "marketplace", "Marketplace"
    ACCOUNT = "account", "Account"


class NotificationTypeChoices(models.TextChoices):
    # Account notifications
    ACCOUNT_VERIFIED = "account_verified", "Account Verified"
    ROLE_APPROVED = "role_approved", "Role Approved"
    ROLE_REJECTED = "role_rejected", "Role Rejected"
    PASSWORD_RESET = "password_reset", "Password Reset"

    # Task notifications
    TASK_ASSIGNED = "task_assigned", "Task Assigned"
    TASK_COMPLETED = "task_completed", "Task Completed"
    TASK_REVIEWED = "task_reviewed", "Task Reviewed"
    ADJUDICATION_REQUIRED = "adjudication_required", "Adjudication Required"

    # Marketplace and payout notifications
    DATASET_PURCHASED = "dataset_purchased", "Dataset Purchased"
    DATASET_SOLD = "dataset_sold", "Dataset Sold"
    PAYOUT_PROCESSED = "payout_processed", "Payout Processed"
    WITHDRAWAL_UPDATE = "withdrawal_update", "Withdrawal Update"

    # System notifications
    MAINTENANCE = "maintenance", "Maintenance"
    SECURITY_ALERT = "security_alert", "Security Alert"
    FEATURE_UPDATE = "feature_update", "Feature Update"