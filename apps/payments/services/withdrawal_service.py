from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.payments.models import (
    WithdrawalMethodChoices,
    PayoutRule,
    Wallet,
    WithdrawalRequest,
    WithdrawalStatusChoices,
)
from apps.payments.services.chapa_client import ChapaClient, ChapaClientError
from apps.scoring.models import UserScore
from apps.users.models.roles import RoleChoices


class WithdrawalService:
    """Service for on-demand score-to-money conversion and withdrawal processing."""

    def __init__(self, chapa_client: ChapaClient | None = None):
        self.chapa_client = chapa_client or ChapaClient()

    @staticmethod
    def get_payout_rule(*, user) -> PayoutRule:
        """Fetch the currently active payout rule for the user's role."""
        rule = PayoutRule.objects.filter(
            role=user.role,
            active=True
        ).first()
        if not rule:
            raise ValidationError(
                {
                    "detail": f"No active payout rule configured for role {user.role}."
                }
            )
        return rule

    @staticmethod
    def calculate_withdrawable_amount(user) -> dict:
        """
        Calculate withdrawable amount for a user based on their score and payout rule.
        
        Returns:
            dict with keys:
                - available_points: points available for withdrawal (total - locked)
                - conversion_rate: score-to-currency rate from payout rule
                - withdrawable_amount: available_points * conversion_rate
                - minimum_amount: minimum withdrawal amount from payout rule
                - meets_minimum: whether withdrawable_amount meets minimum
                - currency: user's wallet currency
        """
        rule = WithdrawalService.get_payout_rule(user=user)
        
        try:
            user_score = UserScore.objects.get(user=user)
        except UserScore.DoesNotExist:
            raise ValidationError({"detail": "User has no score record."})
        
        wallet, _ = Wallet.objects.get_or_create(user=user)
        
        available_points = user_score.available_points
        withdrawable_amount = Decimal(str(available_points)) * rule.score_to_currency_rate
        lifetime_points_earned = max(0, int(user_score.total_points))
        total_earned_amount = Decimal(str(lifetime_points_earned)) * rule.score_to_currency_rate
        meets_minimum = withdrawable_amount >= rule.minimum_withdrawal_amount
        display_available_balance = max(Decimal("0"), withdrawable_amount - wallet.pending_balance)
        
        return {
            "available_points": available_points,
            "total_points": user_score.total_points,
            "locked_points": user_score.locked_points,
            "conversion_rate": float(rule.score_to_currency_rate),
            "withdrawable_amount": float(withdrawable_amount),
            "minimum_amount": float(rule.minimum_withdrawal_amount),
            "meets_minimum": meets_minimum,
            "currency": wallet.currency,
            "wallet_available_balance": float(display_available_balance),
            "wallet_pending_balance": float(wallet.pending_balance),
            "wallet_total_earned": float(total_earned_amount),
            "wallet_total_withdrawn": float(wallet.total_withdrawn),
        }

    @transaction.atomic
    def initiate_withdrawal_request(
        self,
        *,
        user,
        bank_code: str,
        account_number: str,
        account_name: str,
        amount: Decimal,
    ) -> dict:
        """
        Initiate a withdrawal request with on-demand calculation and point locking.
        
        Steps:
        1. Validate user is a scoring role (contributor, annotator, expert)
        2. Fetch payout rule for user's role
        3. Calculate if amount is valid
        4. Lock required points
        5. Create WithdrawalRequest with PENDING status
        6. Return request for next phase (Chapa transfer initiation)
        """
        withdrawal_request = None
        try:
            withdrawal_request, wallet, rule, required_points = WithdrawalService._create_pending_withdrawal_request(
                user=user,
                bank_code=bank_code,
                account_number=account_number,
                account_name=account_name,
                amount=amount,
            )

            transfer_reference = WithdrawalService._build_transfer_reference(
                withdrawal_request=withdrawal_request
            )
            transfer_payload = WithdrawalService._build_transfer_payload(
                withdrawal_request=withdrawal_request,
                wallet=wallet,
                rule=rule,
                transfer_reference=transfer_reference,
            )
            transfer_response = self.chapa_client.initiate_transfer(transfer_payload)
            provider_status = WithdrawalService._extract_provider_status(transfer_response)

            with transaction.atomic():
                withdrawal_request = WithdrawalRequest.objects.select_for_update().get(
                    pk=withdrawal_request.pk
                )
                withdrawal_request.metadata = {
                    **(withdrawal_request.metadata or {}),
                    "transfer_reference": transfer_reference,
                    "transfer_initiate_response": transfer_response,
                    "transfer_initiate_status": provider_status,
                }

                if WithdrawalService._is_transfer_accepted(transfer_response):
                    withdrawal_request.status = WithdrawalStatusChoices.APPROVED
                else:
                    withdrawal_request.status = WithdrawalStatusChoices.PENDING

                withdrawal_request.save(update_fields=["status", "metadata"])

            verification_response = None
            if WithdrawalService._is_transfer_terminal_success(transfer_response):
                verification_response = self.verify_and_finalize_transfer(
                    tx_ref=transfer_reference
                )

            return {
                "withdrawal_request": withdrawal_request,
                "transfer_reference": transfer_reference,
                "transfer_response": transfer_response,
                "verification_response": verification_response,
            }
        except ChapaClientError as exc:
            if withdrawal_request is not None:
                WithdrawalService.release_withdrawal_hold(
                    withdrawal_request=withdrawal_request,
                    failure_reason=str(exc),
                )
            raise ValidationError({"detail": f"Chapa transfer failed: {exc}"})

    @staticmethod
    @transaction.atomic
    def release_locked_points(*, user, points: int) -> None:
        """Release locked points back to available (if withdrawal fails)."""
        try:
            user_score = UserScore.objects.select_for_update().get(user=user)
        except UserScore.DoesNotExist:
            return

        user_score.locked_points = max(0, user_score.locked_points - points)
        user_score.save(update_fields=["locked_points"])

    @staticmethod
    @transaction.atomic
    def release_withdrawal_hold(*, withdrawal_request: WithdrawalRequest, failure_reason: str | None = None) -> None:
        """Release a pending withdrawal hold if transfer initiation or verification fails."""
        wallet = withdrawal_request.wallet
        wallet.pending_balance = max(0, wallet.pending_balance - withdrawal_request.amount)
        wallet.save(update_fields=["pending_balance"])

        metadata = withdrawal_request.metadata or {}
        points_locked = metadata.get("points_locked", 0)
        if points_locked:
            WithdrawalService.release_locked_points(user=withdrawal_request.user, points=points_locked)

        withdrawal_request.status = WithdrawalStatusChoices.FAILED
        withdrawal_request.processed_at = timezone.now()
        withdrawal_request.metadata = {
            **metadata,
            "failure_reason": failure_reason or metadata.get("failure_reason"),
            "reverted_at": timezone.now().isoformat(),
        }
        withdrawal_request.save(update_fields=["status", "processed_at", "metadata"])

    @staticmethod
    @transaction.atomic
    def finalize_withdrawal(
        *,
        withdrawal_request: WithdrawalRequest,
        transfer_reference: str,
    ) -> None:
        """
        Finalize withdrawal after successful Chapa transfer.
        
        - Mark WithdrawalRequest as COMPLETED
        - Move amount to wallet.total_withdrawn
        - Permanently consume locked points
        """
        withdrawal_request.status = WithdrawalStatusChoices.COMPLETED
        withdrawal_request.processed_at = timezone.now()
        withdrawal_request.metadata = {
            **(withdrawal_request.metadata or {}),
            "transfer_reference": transfer_reference,
            "completed_at": timezone.now().isoformat(),
        }
        withdrawal_request.save(
            update_fields=["status", "processed_at", "metadata"]
        )

        # Update wallet: deduct from pending_balance if any, increment total_withdrawn
        wallet = withdrawal_request.wallet
        wallet.pending_balance = max(0, wallet.pending_balance - withdrawal_request.amount)
        wallet.total_withdrawn += withdrawal_request.amount
        wallet.save(update_fields=["pending_balance", "total_withdrawn"])

        # Permanently consume the locked points (no going back)
        metadata = withdrawal_request.metadata or {}
        points_locked = metadata.get("points_locked", 0)
        if points_locked:
            user_score = withdrawal_request.user.user_score
            user_score.locked_points = max(0, user_score.locked_points - points_locked)
            user_score.save(update_fields=["locked_points"])

    @staticmethod
    def verify_and_finalize_transfer(*, tx_ref: str) -> dict:
        """Verify a Chapa transfer and finalize the withdrawal if successful."""
        if not tx_ref:
            raise ValidationError({"detail": "tx_ref is required."})

        withdrawal_request = (
            WithdrawalRequest.objects.select_related("user", "wallet")
            .filter(metadata__transfer_reference=tx_ref)
            .first()
        )
        if not withdrawal_request:
            raise ValidationError({"detail": "Withdrawal request not found for this transfer reference."})

        verify_response = ChapaClient().verify_transfer(tx_ref)
        if not WithdrawalService._is_transfer_successful(verify_response):
            with transaction.atomic():
                withdrawal_request = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal_request.pk)
                metadata = withdrawal_request.metadata or {}
                withdrawal_request.metadata = {
                    **metadata,
                    "transfer_verify_response": verify_response,
                    "transfer_verify_status": WithdrawalService._extract_provider_status(verify_response),
                    "failure_reason": "Transfer verification failed",
                }
                withdrawal_request.save(update_fields=["metadata"])
            WithdrawalService.release_withdrawal_hold(
                withdrawal_request=withdrawal_request,
                failure_reason="Transfer verification failed",
            )
            raise ValidationError({"detail": "Transfer verification failed.", "provider_response": verify_response})

        WithdrawalService.finalize_withdrawal(
            withdrawal_request=withdrawal_request,
            transfer_reference=tx_ref,
        )
        return {
            "withdrawal_request": withdrawal_request,
            "provider_response": verify_response,
            "transfer_reference": tx_ref,
        }

    @staticmethod
    def _create_pending_withdrawal_request(
        *,
        user,
        bank_code: str,
        account_number: str,
        account_name: str,
        amount: Decimal,
    ) -> tuple[WithdrawalRequest, Wallet, PayoutRule, int]:
        if not hasattr(user, "role") or user.role not in {
            RoleChoices.CONTRIBUTOR,
            RoleChoices.ANNOTATOR,
            RoleChoices.EXPERT,
        }:
            raise ValidationError(
                {"detail": "Only contributors, annotators, and experts can withdraw."}
            )

        rule = WithdrawalService.get_payout_rule(user=user)

        with transaction.atomic():
            try:
                user_score = UserScore.objects.select_for_update().get(user=user)
            except UserScore.DoesNotExist:
                raise ValidationError({"detail": "User has no score record."})

            wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)

            if user_score.available_points < rule.minimum_points_required:
                raise ValidationError(
                    {
                        "detail": f"Minimum {rule.minimum_points_required} points required to withdraw.",
                        "available_points": user_score.available_points,
                    }
                )

            if amount < rule.minimum_withdrawal_amount:
                raise ValidationError(
                    {
                        "detail": f"Minimum withdrawal amount is {rule.minimum_withdrawal_amount} {wallet.currency}.",
                        "minimum_amount": float(rule.minimum_withdrawal_amount),
                    }
                )

            points_decimal = amount / rule.score_to_currency_rate
            if points_decimal != points_decimal.to_integral_value():
                raise ValidationError(
                    {
                        "detail": (
                            "Withdrawal amount must be an exact multiple of the role conversion rate. "
                            f"For role {user.role}, the rate is {rule.score_to_currency_rate}."
                        ),
                        "score_to_currency_rate": float(rule.score_to_currency_rate),
                    }
                )

            required_points = int(points_decimal)
            if required_points > user_score.available_points:
                raise ValidationError(
                    {
                        "detail": "Insufficient available points for this withdrawal amount.",
                        "available_points": user_score.available_points,
                        "required_points": required_points,
                    }
                )

            user_score.locked_points += required_points
            user_score.save(update_fields=["locked_points"])

            wallet.pending_balance += amount
            wallet.save(update_fields=["pending_balance"])

            withdrawal_request = WithdrawalRequest.objects.create(
                user=user,
                wallet=wallet,
                amount=amount,
                payment_method=WithdrawalMethodChoices.BANK_TRANSFER,
                payment_details={
                    "bank_code": bank_code,
                    "account_number": account_number,
                    "account_name": account_name,
                },
                status=WithdrawalStatusChoices.PENDING,
                metadata={
                    "points_locked": required_points,
                    "conversion_rate": float(rule.score_to_currency_rate),
                    "user_role": user.role,
                    "initiated_at": timezone.now().isoformat(),
                },
            )

        return withdrawal_request, wallet, rule, required_points

    @staticmethod
    def _build_transfer_reference(*, withdrawal_request: WithdrawalRequest) -> str:
        return f"WD-{withdrawal_request.id}-{uuid4().hex[:8].upper()}"

    @staticmethod
    def _build_transfer_payload(
        *,
        withdrawal_request: WithdrawalRequest,
        wallet: Wallet,
        rule: PayoutRule,
        transfer_reference: str,
    ) -> dict:
        payment_details = withdrawal_request.payment_details or {}
        return {
            "account_name": payment_details.get("account_name"),
            "account_number": payment_details.get("account_number"),
            "amount": str(withdrawal_request.amount),
            "currency": wallet.currency,
            "reference": transfer_reference,
            "bank_code": payment_details.get("bank_code"),
            "metadata": {
                "withdrawal_request_id": str(withdrawal_request.id),
                "user_id": str(withdrawal_request.user_id),
                "user_role": withdrawal_request.user.role,
                "score_to_currency_rate": str(rule.score_to_currency_rate),
            },
        }

    @staticmethod
    def _extract_provider_status(provider_response: dict) -> str:
        if not isinstance(provider_response, dict):
            return "unknown"
        status_value = provider_response.get("status")
        if status_value:
            return str(status_value)
        data = provider_response.get("data")
        if isinstance(data, dict) and data.get("status"):
            return str(data.get("status"))
        return "unknown"

    @staticmethod
    def _is_transfer_accepted(provider_response: dict) -> bool:
        status_value = WithdrawalService._extract_provider_status(provider_response).lower()
        return status_value in {"success", "pending", "queued", "processing", "approved"}

    @staticmethod
    def _is_transfer_terminal_success(provider_response: dict) -> bool:
        status_value = WithdrawalService._extract_provider_status(provider_response).lower()
        data = provider_response.get("data") if isinstance(provider_response, dict) else None
        data_status = str(data.get("status") if isinstance(data, dict) else "").lower()
        return status_value in {"success", "successful"} or data_status in {"success", "successful", "completed", "paid"}

    @staticmethod
    def _is_transfer_successful(provider_response: dict) -> bool:
        status_value = WithdrawalService._extract_provider_status(provider_response).lower()
        data = provider_response.get("data") if isinstance(provider_response, dict) else None
        data_status = str(data.get("status") if isinstance(data, dict) else "").lower()
        return status_value in {"success", "successful"} or data_status in {"success", "successful", "completed", "paid"}
