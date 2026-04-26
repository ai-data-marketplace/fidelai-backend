from django.db import models

from apps.common.models.base import TimeStampedModel

from .choices import TransactionStatusChoices, TransactionTypeChoices


class PaymentTransaction(TimeStampedModel):
	user = models.ForeignKey(
		"users.CustomUser",
		on_delete=models.PROTECT,
		related_name="payment_transactions",
	)
	wallet = models.ForeignKey(
		"payments.Wallet",
		on_delete=models.PROTECT,
		related_name="transactions",
	)
	transaction_type = models.CharField(
		max_length=20,
		choices=TransactionTypeChoices.choices,
	)
	status = models.CharField(
		max_length=20,
		choices=TransactionStatusChoices.choices,
		default=TransactionStatusChoices.PENDING,
	)
	amount = models.DecimalField(max_digits=14, decimal_places=2)

	related_scorelog = models.ForeignKey(
		"scoring.ScoreLog",
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name="payment_transactions",
	)
	related_dataset = models.ForeignKey(
		"datasets.Dataset",
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name="payment_transactions",
	)
	related_order = models.ForeignKey(
		"marketplace.Order",
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name="payment_transactions",
	)

	description = models.CharField(max_length=255, blank=True)
	metadata = models.JSONField(blank=True, null=True)
	processed_at = models.DateTimeField(blank=True, null=True)

	class Meta:
		ordering = ("-created_at",)
		constraints = [
			models.CheckConstraint(
				condition=models.Q(amount__gte=0),
				name="chk_payment_transaction_amount_non_negative",
			),
			models.CheckConstraint(
				condition=(
					models.Q(status=TransactionStatusChoices.COMPLETED, processed_at__isnull=False)
					| ~models.Q(status=TransactionStatusChoices.COMPLETED)
				),
				name="chk_payment_transaction_completed_requires_processed_at",
			),
		]
		indexes = [
			# user_id and wallet_id are indexed by Django ForeignKey automatically.
			models.Index(fields=["transaction_type"]),
			models.Index(fields=["status"]),
			models.Index(fields=["created_at"]),
			models.Index(fields=["user", "created_at"]),
			models.Index(fields=["wallet", "created_at"]),
		]

	def __str__(self):
		return f"PaymentTransaction<{self.user_id}:{self.transaction_type}:{self.amount}>"
