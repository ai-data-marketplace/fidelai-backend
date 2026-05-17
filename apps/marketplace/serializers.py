from __future__ import annotations

from rest_framework import serializers

from apps.datasets.models.dataset import Dataset
from apps.datasets.models.assets import DatasetAsset, DatasetFileFormatChoices
from apps.datasets.models.metrics import DatasetMetrics
from apps.marketplace.services.dataset_detail_service import DatasetDetailService
from apps.marketplace.models import DatasetPurchase, PurchaseAccessStatusChoices, Order


class DatasetAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetAsset
        fields = ("id", "file_format", "file_size_bytes")


class DatasetMetricsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetMetrics
        fields = (
            "total_documents",
            "chunk_count",
            "token_count",
            "avg_qc_score",
            "annotation_coverage",
            "expert_validation_ratio",
            "dataset_size_bytes",
            "label_distribution",
            "domain_distribution",
            "computed_at",
        )


class DatasetListSerializer(serializers.ModelSerializer):
    metrics = DatasetMetricsSerializer(read_only=True)
    assets = DatasetAssetSerializer(many=True, read_only=True)
    created_by = serializers.CharField(source="created_by.email", read_only=True)

    class Meta:
        model = Dataset
        fields = (
            "id",
            "title",
            "description",
            "domain",
            "subdomain",
            "language",
            "license_type",
            "nlp_task_type",
            "price",
            "version",
            "status",
            "collection_year",
            "created_at",
            "created_by",
            "metrics",
            "assets",
        )


class DatasetDetailSerializer(DatasetListSerializer):
    build_config = serializers.JSONField(read_only=True)
    approved_by = serializers.CharField(source="approved_by.email", read_only=True)
    approved_at = serializers.DateTimeField(read_only=True)
    samples = serializers.SerializerMethodField()
    sample_quality_scores = serializers.SerializerMethodField()
    total_contributors = serializers.SerializerMethodField()
    has_active_purchase = serializers.SerializerMethodField()
    purchase_status = serializers.SerializerMethodField()

    class Meta(DatasetListSerializer.Meta):
        fields = DatasetListSerializer.Meta.fields + (
            "build_config",
            "approved_by",
            "approved_at",
            "samples",
            "sample_quality_scores",
            "total_contributors",
            "has_active_purchase",
            "purchase_status",
        )

    def _get_enrichment(self, obj):
        """Cache enrichment data to avoid multiple service calls."""
        if not hasattr(self, "_enrichment_cache"):
            service = DatasetDetailService()
            self._enrichment_cache = service.enrich_dataset_detail(dataset=obj, sample_limit=10)
        return self._enrichment_cache

    def get_samples(self, obj):
        """Fetch enriched dataset details including samples."""
        enrichment = self._get_enrichment(obj)
        return enrichment["samples"]

    def get_sample_quality_scores(self, obj):
        """Fetch quality scores for samples."""
        enrichment = self._get_enrichment(obj)
        return enrichment["sample_quality_scores"]

    def get_total_contributors(self, obj):
        """Fetch contributor count."""
        enrichment = self._get_enrichment(obj)
        return enrichment["total_contributors"]

    def get_has_active_purchase(self, obj):
        request = self.context.get("request") if hasattr(self, "context") else None
        if not request or not getattr(request, "user", None) or request.user.is_anonymous:
            return False
        return DatasetPurchase.objects.filter(
            buyer=request.user, dataset=obj, access_status=PurchaseAccessStatusChoices.ACTIVE
        ).exists()

    def get_purchase_status(self, obj):
        """Return purchase status based on Order payment status (source of truth)."""
        request = self.context.get("request") if hasattr(self, "context") else None
        if not request or not getattr(request, "user", None) or request.user.is_anonymous:
            return None
        
        # Check for Order (primary source of truth for payment status)
        order = Order.objects.filter(
            buyer=request.user, items__dataset=obj
        ).order_by("-created_at").first()
        
        if order:
            if order.payment_status == "paid":
                return "active"
            elif order.payment_status == "pending":
                return "pending"
            elif order.payment_status == "failed":
                return "failed"
            else:
                return order.payment_status
        
        # Fallback to DatasetPurchase if no order exists (shouldn't happen normally)
        purchase = DatasetPurchase.objects.filter(
            buyer=request.user, dataset=obj
        ).order_by("-purchased_at").first()
        
        return purchase.access_status if purchase else None


class DatasetPurchaseInitSerializer(serializers.Serializer):
    order_number = serializers.CharField()
    tx_ref = serializers.CharField()
    checkout_url = serializers.URLField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    dataset_id = serializers.UUIDField()
    dataset_title = serializers.CharField()


class InventoryPurchaseSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order_item.order.order_number", read_only=True)
    dataset_id = serializers.UUIDField(source="dataset.id", read_only=True)
    dataset_title = serializers.CharField(source="dataset.title", read_only=True)
    price = serializers.DecimalField(source="order_item.price_at_purchase", max_digits=12, decimal_places=2, read_only=True)
    license = serializers.CharField(source="order_item.license_type_at_purchase", read_only=True)
    status = serializers.SerializerMethodField()
    assets = DatasetAssetSerializer(source="dataset.assets", many=True, read_only=True)

    class Meta:
        model = DatasetPurchase
        fields = (
            "id",
            "order_number",
            "dataset_id",
            "dataset_title",
            "purchased_at",
            "price",
            "license",
            "status",
            "assets",
            "download_count",
            "last_downloaded_at",
        )

    def get_status(self, obj):
        order = getattr(getattr(obj, "order_item", None), "order", None)
        if order and getattr(order, "payment_status", None):
            return order.payment_status
        return obj.access_status
