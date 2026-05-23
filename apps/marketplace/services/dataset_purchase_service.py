from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.datasets.models.dataset import Dataset, DatasetStatusChoices
from apps.marketplace.models import (
    DatasetPurchase,
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentStatusChoices,
    PurchaseAccessStatusChoices,
)
from apps.payments.models import (
    PaymentTransaction,
    TransactionStatusChoices,
    TransactionTypeChoices,
    Wallet,
)
from apps.payments.services.chapa_client import ChapaClient, ChapaClientError
from apps.users.models.roles import RoleChoices
from apps.notifications.services.notification_service import notify_dataset_purchased, notify_dataset_sold
from apps.scoring.services import score_dataset_sold


class DatasetPurchaseService:
    def __init__(self, chapa_client: ChapaClient | None = None):
        self.chapa_client = chapa_client or ChapaClient()

    @transaction.atomic
    def initialize_purchase(self, *, buyer, dataset: Dataset, request=None) -> dict:
        self._validate_buyer(buyer=buyer)
        self._validate_dataset(dataset=dataset)

        if DatasetPurchase.objects.filter(buyer=buyer, dataset=dataset, access_status=PurchaseAccessStatusChoices.ACTIVE).exists():
            raise ValidationError({"detail": "You already have active access to this dataset."})

        order_number = self._build_order_number()
        tx_ref = self._build_tx_ref(order_number=order_number)
        amount = Decimal(str(dataset.price))
        currency = getattr(settings, "CHAPA_DEFAULT_CURRENCY", "ETB")

        order = Order.objects.create(
            buyer=buyer,
            order_number=order_number,
            total_amount=amount,
            currency=currency,
            order_status=OrderStatusChoices.PENDING,
            payment_status=PaymentStatusChoices.PENDING,
            payment_reference=tx_ref,
            metadata={"provider": "chapa", "tx_ref": tx_ref, "dataset_id": str(dataset.id)},
        )
        order_item = OrderItem.objects.create(
            order=order,
            dataset=dataset,
            price_at_purchase=amount,
            license_type_at_purchase=dataset.license_type,
        )

        wallet = self._get_or_create_wallet(user=buyer)
        PaymentTransaction.objects.create(
            user=buyer,
            wallet=wallet,
            transaction_type=TransactionTypeChoices.ADJUSTMENT,
            status=TransactionStatusChoices.PENDING,
            amount=amount,
            related_dataset=dataset,
            related_order=order,
            description=f"Dataset purchase initiation for {dataset.title}",
            metadata={
                "provider": "chapa",
                "tx_ref": tx_ref,
                "direction": "debit",
                "purpose": "dataset_purchase",
            },
        )

        callback_url = self._build_callback_url(request=request)
        return_url = self._build_return_url(dataset=dataset)
        customer_first_name, customer_last_name = self._split_name(getattr(buyer, "full_name", "Buyer"))

        chapa_payload = {
            "amount": str(amount),
            "currency": currency,
            "email": buyer.email,
            "first_name": customer_first_name,
            "last_name": customer_last_name,
            "tx_ref": tx_ref,
            "callback_url": callback_url,
            "return_url": return_url,
            "customization[title]": dataset.title,
            "customization[description]": dataset.description[:255],
            "metadata": {
                "order_id": str(order.id),
                "order_number": order.order_number,
                "dataset_id": str(dataset.id),
                "buyer_id": str(buyer.id),
            },
        }

        try:
            chapa_response = self.chapa_client.initialize_transaction(chapa_payload)
        except ChapaClientError:
            raise

        checkout_url = self._extract_checkout_url(chapa_response)
        order.metadata = {
            **(order.metadata or {}),
            "chapa_initialize_response": chapa_response,
            "checkout_url": checkout_url,
        }
        order.save(update_fields=["metadata"])

        return {
            "order": order,
            "order_item": order_item,
            "tx_ref": tx_ref,
            "checkout_url": checkout_url,
            "chapa_response": chapa_response,
        }

    @transaction.atomic
    def verify_and_finalize(self, *, tx_ref: str) -> dict:
        if not tx_ref:
            raise ValidationError({"detail": "tx_ref is required."})

        order = (
            Order.objects.select_related("buyer")
            .prefetch_related("items__dataset")
            .filter(Q(payment_reference=tx_ref) | Q(metadata__tx_ref=tx_ref))
            .first()
        )
        if not order:
            raise ValidationError({"detail": "Order not found for this transaction reference."})

        chapa_result = self.chapa_client.verify_transaction(tx_ref)
        if not self._is_successful_chapa_result(chapa_result):
            raise ValidationError({"detail": "Payment verification failed.", "provider_response": chapa_result})

        order_item = order.items.first()
        if not order_item:
            raise ValidationError({"detail": "Order item missing for this order."})

        purchase, _ = DatasetPurchase.objects.update_or_create(
            buyer=order.buyer,
            dataset=order_item.dataset,
            order_item=order_item,
            defaults={
                "access_status": PurchaseAccessStatusChoices.ACTIVE,
                "purchased_at": timezone.now(),
            },
        )

        # Send dataset purchased notification to buyer
        notify_dataset_purchased(order.buyer, order_item.dataset)
        # Optionally, notify the dataset owner (seller)
        if hasattr(order_item.dataset, "created_by") and order_item.dataset.created_by:
            notify_dataset_sold(order_item.dataset.created_by, order_item.dataset)

        score_dataset_sold(order_item.dataset)

        order.payment_status = PaymentStatusChoices.PAID
        order.order_status = OrderStatusChoices.COMPLETED
        order.completed_at = timezone.now()
        order.payment_reference = tx_ref
        order.metadata = {**(order.metadata or {}), "chapa_verify_response": chapa_result}
        order.save(update_fields=["payment_status", "order_status", "completed_at", "payment_reference", "metadata"])

        PaymentTransaction.objects.filter(related_order=order).update(
            status=TransactionStatusChoices.COMPLETED,
            processed_at=timezone.now(),
            metadata={"provider": "chapa", "tx_ref": tx_ref, "verify_response": chapa_result},
        )

        return {
            "order": order,
            "order_item": order_item,
            "purchase": purchase,
            "provider_response": chapa_result,
        }

    def _validate_buyer(self, *, buyer) -> None:
        if getattr(buyer, "role", None) != RoleChoices.BUYER:
            raise PermissionDenied("Only buyers can purchase datasets.")

    def _validate_dataset(self, *, dataset: Dataset) -> None:
        if dataset.status not in {DatasetStatusChoices.APPROVED, DatasetStatusChoices.PUBLISHED}:
            raise ValidationError({"detail": "This dataset is not available for purchase."})

    def _get_or_create_wallet(self, *, user) -> Wallet:
        wallet, _ = Wallet.objects.get_or_create(user=user)
        return wallet

    def _build_order_number(self) -> str:
        return f"ORD-{uuid4().hex[:12].upper()}"

    def _build_tx_ref(self, *, order_number: str) -> str:
        return f"CHAPA-{order_number}-{uuid4().hex[:8].upper()}"

    def _build_callback_url(self, *, request=None) -> str:
        callback_path = reverse("payments-chapa-callback")
        if request is not None:
            return request.build_absolute_uri(callback_path)
        return f"{getattr(settings, 'FRONTEND_URL', '').rstrip('/')}{callback_path}"

    def _build_return_url(self, *, dataset: Dataset) -> str:
        frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
        return f"{frontend_url}/buyer/marketplace/{dataset.id}"

    def _split_name(self, full_name: str) -> tuple[str, str]:
        parts = (full_name or "Buyer").strip().split()
        if not parts:
            return "Buyer", "User"
        if len(parts) == 1:
            return parts[0], "User"
        return parts[0], " ".join(parts[1:])

    def _extract_checkout_url(self, chapa_response: dict) -> str:
        data = chapa_response.get("data") if isinstance(chapa_response, dict) else {}
        if isinstance(data, dict):
            checkout_url = data.get("checkout_url") or data.get("checkoutUrl") or data.get("url")
            if checkout_url:
                return checkout_url
        raise ValidationError({"detail": "Chapa did not return a checkout URL.", "provider_response": chapa_response})

    def _is_successful_chapa_result(self, chapa_result: dict) -> bool:
        if not isinstance(chapa_result, dict):
            return False
        if chapa_result.get("status") in {"success", True}:
            return True
        data = chapa_result.get("data")
        if isinstance(data, dict):
            return data.get("status") in {"success", "successful", True, "paid"}
        return False
