from apps.users.models.roles import RoleChoices
from django.db import models

from apps.common.models.base import TimeStampedModel

from .choices import CommissionRoleChoices, WithdrawalMethodChoices, WithdrawalStatusChoices


class WithdrawalRequest(TimeStampedModel):
    user = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="withdrawal_requests",
    )
    wallet = models.ForeignKey(
        "payments.Wallet",
        on_delete=models.PROTECT,
        related_name="withdrawal_requests",
    )

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(
        max_length=30, choices=WithdrawalMethodChoices.choices)
    payment_details = models.JSONField()

    status = models.CharField(
        max_length=20,
        choices=WithdrawalStatusChoices.choices,
        default=WithdrawalStatusChoices.PENDING,
    )

    reviewed_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_withdrawal_requests",
    )
    admin_notes = models.TextField(blank=True)
    metadata = models.JSONField(blank=True, null=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-requested_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="chk_withdrawal_request_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=WithdrawalStatusChoices.COMPLETED,
                             processed_at__isnull=False)
                    | ~models.Q(status=WithdrawalStatusChoices.COMPLETED)
                ),
                name="chk_withdrawal_request_completed_requires_processed_at",
            ),
        ]
        indexes = [
            # user_id is indexed by Django ForeignKey automatically.
            models.Index(fields=["status"]),
            models.Index(fields=["requested_at"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"WithdrawalRequest<{self.user_id}:{self.amount}:{self.status}>"


class CommissionConfig(TimeStampedModel):
    role = models.CharField(
        max_length=20, choices=CommissionRoleChoices.choices)
    commission_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("role", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(commission_percentage__gte=0) & models.Q(
                    commission_percentage__lte=100),
                name="chk_commission_config_percentage_range",
            ),
            models.UniqueConstraint(
                fields=["role"],
                condition=models.Q(active=True),
                name="uniq_active_commission_config_per_role",
            ),
        ]
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["active"]),
        ]

    def __str__(self):
        return f"CommissionConfig<{self.role}:{self.commission_percentage}:{self.active}>"


class PayoutRule(TimeStampedModel):

    minimum_points_required = models.PositiveIntegerField(default=0)
    minimum_withdrawal_amount = models.DecimalField(
        max_digits=14, decimal_places=2)
    score_to_currency_rate = models.DecimalField(
        max_digits=14, decimal_places=6)
    active = models.BooleanField(default=True)
    role = models.CharField(
        max_length=20, choices=RoleChoices.choices)

    class Meta:
        ordering = ("-created_at",)
        constraints = [ 
            models.CheckConstraint(
                condition=models.Q(minimum_withdrawal_amount__gte=0),
                name="chk_payout_rule_minimum_withdrawal_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(score_to_currency_rate__gt=0),
                name="chk_payout_rule_score_to_currency_rate_positive",
            ),
            models.UniqueConstraint(
                fields=["role", "active"],
                condition=models.Q(active=True),
                name="uniq_active_payout_rule_per_role",
            ),
        ]
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["active"]),
            models.Index(fields=["role", "active"]),
        ]

    def __str__(self):
        return (
            f"PayoutRule<points:{self.minimum_points_required}:"
            f"min:{self.minimum_withdrawal_amount}:rate:{self.score_to_currency_rate}:{self.active}>"
        )
