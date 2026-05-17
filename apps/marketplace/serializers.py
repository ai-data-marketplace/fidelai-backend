from __future__ import annotations

from rest_framework import serializers

from apps.datasets.models.dataset import Dataset
from apps.datasets.models.assets import DatasetAsset, DatasetFileFormatChoices
from apps.datasets.models.metrics import DatasetMetrics
from apps.marketplace.services.dataset_detail_service import DatasetDetailService


class DatasetAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetAsset
        fields = ("file_format", "file", "file_size_bytes")


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

    class Meta(DatasetListSerializer.Meta):
        fields = DatasetListSerializer.Meta.fields + (
            "build_config",
            "approved_by",
            "approved_at",
            "samples",
            "sample_quality_scores",
            "total_contributors",
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
