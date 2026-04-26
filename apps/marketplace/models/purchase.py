from django.db import models

from apps.common.models.base import TimeStampedModel
from apps.users.models.roles import RoleChoices

from .choices import PurchaseAccessStatusChoices


class DatasetPurchase(TimeStampedModel):
    buyer = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="dataset_purchases",
        limit_choices_to={"role": RoleChoices.BUYER},
    )
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.PROTECT,
        related_name="dataset_purchases",
    )
    order_item = models.ForeignKey(
        "marketplace.OrderItem",
        on_delete=models.PROTECT,
        related_name="dataset_purchases",
    )

    purchased_at = models.DateTimeField(auto_now_add=True)
    access_status = models.CharField(
        max_length=20,
        choices=PurchaseAccessStatusChoices.choices,
        default=PurchaseAccessStatusChoices.ACTIVE,
    )

    download_count = models.PositiveIntegerField(default=0)
    last_downloaded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-purchased_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["buyer", "dataset", "order_item"],
                name="uniq_dataset_purchase_buyer_dataset_order_item",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(download_count=0, last_downloaded_at__isnull=True)
                    | models.Q(download_count__gt=0)
                ),
                name="chk_dataset_purchase_download_count_last_downloaded_consistency",
            ),
        ]
        indexes = [
            # buyer_id and dataset_id are indexed by Django ForeignKey automatically.
            models.Index(fields=["access_status"]),
            models.Index(fields=["buyer", "access_status"]),
            models.Index(fields=["dataset", "access_status"]),
        ]

    def __str__(self):
        return f"DatasetPurchase<{self.buyer_id}:{self.dataset_id}:{self.access_status}>"