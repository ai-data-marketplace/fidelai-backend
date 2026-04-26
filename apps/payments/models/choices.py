from django.db import models


class TransactionTypeChoices(models.TextChoices):
    EARNING = "earning", "Earning"
    BONUS = "bonus", "Bonus"
    COMMISSION = "commission", "Commission"
    WITHDRAWAL = "withdrawal", "Withdrawal"
    REFUND = "refund", "Refund"
    ADJUSTMENT = "adjustment", "Adjustment"


class TransactionStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class WithdrawalMethodChoices(models.TextChoices):
    BANK_TRANSFER = "bank_transfer", "Bank Transfer"
    TELEBIRR = "telebirr", "Telebirr"
    MOBILE_MONEY = "mobile_money", "Mobile Money"
    PAYPAL = "paypal", "PayPal"


class WithdrawalStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class CommissionRoleChoices(models.TextChoices):
    CONTRIBUTOR = "contributor", "Contributor"
    ANNOTATOR = "annotator", "Annotator"
    EXPERT = "expert", "Expert"
    PLATFORM = "platform", "Platform"