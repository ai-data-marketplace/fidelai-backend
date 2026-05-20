from rest_framework import serializers

from apps.payments.models import PayoutRule


class PayoutRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutRule
        fields = [
            "id",
            "role",
            "minimum_points_required",
            "minimum_withdrawal_amount",
            "score_to_currency_rate",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def validate_minimum_points_required(self, value):
        if value < 0:
            raise serializers.ValidationError("Minimum points cannot be negative.")
        return value
    
    def validate_minimum_withdrawal_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Minimum withdrawal amount must be greater than 0.")
        return value
    
    def validate_score_to_currency_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError("Score to currency rate must be greater than 0.")
        return value
    
    def validate(self, attrs):
        if attrs.get("active") and self.instance is None:
            existing = PayoutRule.objects.filter(
                role=attrs.get("role"),
                active=True
            ).exists()
            if existing:
                raise serializers.ValidationError(
                    f"An active payout rule already exists for role {attrs.get('role')}. "
                    f"Deactivate the existing rule first."
                )
        
        return attrs
