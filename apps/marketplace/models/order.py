from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.users.models.roles import RoleChoices

from .choices import OrderStatusChoices, PaymentStatusChoices


class Order(TimeStampedModel):
    buyer = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="marketplace_orders",
        limit_choices_to={"role": RoleChoices.BUYER},
    )
    order_number = models.CharField(max_length=64, unique=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="ETB")

    order_status = models.CharField(
        max_length=20,
        choices=OrderStatusChoices.choices,
        default=OrderStatusChoices.PENDING,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatusChoices.choices,
        default=PaymentStatusChoices.PENDING,
    )

    completed_at = models.DateTimeField(blank=True, null=True)
    payment_reference = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="chk_order_total_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(order_status=OrderStatusChoices.COMPLETED, completed_at__isnull=False)
                    | ~models.Q(order_status=OrderStatusChoices.COMPLETED)
                ),
                name="chk_order_completed_requires_completed_at",
            ),
        ]
        indexes = [
            # buyer_id is indexed by Django ForeignKey automatically.
            # order_number is indexed by unique=True automatically.
            models.Index(fields=["order_status"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["buyer", "created_at"]),
        ]

    def __str__(self):
        return f"Order<{self.order_number}:{self.buyer_id}>"


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(
        "marketplace.Order",
        on_delete=models.CASCADE,
        related_name="items",
    )
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    price_at_purchase = models.DecimalField(max_digits=12, decimal_places=2)
    license_type_at_purchase = models.CharField(max_length=20)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["order", "dataset"],
                name="uniq_order_item_order_dataset",
            ),
            models.CheckConstraint(
                condition=models.Q(price_at_purchase__gte=0),
                name="chk_order_item_price_at_purchase_non_negative",
            ),
        ]
        indexes = [
            # order_id and dataset_id are indexed by Django ForeignKey automatically.
            models.Index(fields=["order", "dataset"]),
        ]

    def __str__(self):
        return f"OrderItem<{self.order_id}:{self.dataset_id}>"