from django.db import models

from apps.common.models.base import TimeStampedModel


class Wallet(TimeStampedModel):
	user = models.OneToOneField(
		"users.CustomUser",
		on_delete=models.PROTECT,
		related_name="wallet",
	)
	available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
	pending_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
	total_earned = models.DecimalField(max_digits=14, decimal_places=2, default=0)
	total_withdrawn = models.DecimalField(max_digits=14, decimal_places=2, default=0)
	currency = models.CharField(max_length=8, default="ETB")

	class Meta:
		ordering = ("-updated_at",)
		constraints = [
			models.CheckConstraint(
				condition=models.Q(available_balance__gte=0),
				name="chk_wallet_available_balance_non_negative",
			),
			models.CheckConstraint(
				condition=models.Q(pending_balance__gte=0),
				name="chk_wallet_pending_balance_non_negative",
			),
			models.CheckConstraint(
				condition=models.Q(total_earned__gte=0),
				name="chk_wallet_total_earned_non_negative",
			),
			models.CheckConstraint(
				condition=models.Q(total_withdrawn__gte=0),
				name="chk_wallet_total_withdrawn_non_negative",
			),
		]
		indexes = [
			# user_id is indexed by Django OneToOneField automatically.
			models.Index(fields=["updated_at"]),
		]

	def __str__(self):
		return f"Wallet<{self.user_id}:{self.currency}>"
