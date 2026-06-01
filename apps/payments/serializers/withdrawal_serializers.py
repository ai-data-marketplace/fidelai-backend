from decimal import Decimal

from rest_framework import serializers

from apps.payments.models import Wallet, WithdrawalRequest, PayoutRule
from apps.payments.services.withdrawal_service import WithdrawalService


class WalletDetailsSerializer(serializers.Serializer):
    """Serializer for wallet details including score and withdrawable amount."""

    available_points = serializers.IntegerField()
    total_points = serializers.IntegerField()
    locked_points = serializers.IntegerField()
    conversion_rate = serializers.FloatField()
    withdrawable_amount = serializers.FloatField()
    minimum_amount = serializers.FloatField()
    meets_minimum = serializers.BooleanField()
    currency = serializers.CharField()
    wallet_available_balance = serializers.FloatField()
    wallet_pending_balance = serializers.FloatField()
    wallet_total_earned = serializers.FloatField()
    wallet_total_withdrawn = serializers.FloatField()


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    """Serializer for withdrawal requests."""

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "amount",
            "payment_method",
            "payment_details",
            "status",
            "requested_at",
            "processed_at",
            "metadata",
        ]
        read_only_fields = [
            "id",
            "status",
            "requested_at",
            "processed_at",
            "metadata",
        ]


class WithdrawalRequestCreateSerializer(serializers.Serializer):
    """Serializer for creating a withdrawal request."""

    bank_code = serializers.CharField(max_length=20)
    account_number = serializers.CharField(max_length=50)
    account_name = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))

    def validate(self, attrs):
        """Validate that user can initiate withdrawal with this amount."""
        user = self.context.get("request").user
        amount = attrs["amount"]

        # Check if amount is valid against payout rule for user's role
        try:
            details = WithdrawalService.calculate_withdrawable_amount(user)
        except Exception as e:
            raise serializers.ValidationError({"detail": str(e)})

        if amount > details["withdrawable_amount"]:
            raise serializers.ValidationError(
                {
                    "detail": f"Insufficient withdrawable amount. Available: {details['withdrawable_amount']} {details['currency']}",
                    "available": details["withdrawable_amount"],
                }
            )

        if not details["meets_minimum"]:
            raise serializers.ValidationError(
                {
                    "detail": f"Withdrawal amount does not meet minimum of {details['minimum_amount']} {details['currency']}.",
                    "minimum_amount": details["minimum_amount"],
                }
            )

        rate = Decimal(str(details["conversion_rate"]))
        points_decimal = amount / rate
        if points_decimal != points_decimal.to_integral_value():
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Withdrawal amount must be an exact multiple of your role conversion rate. "
                        f"Your current rate is {details['conversion_rate']}.")
                }
            )

        return attrs
