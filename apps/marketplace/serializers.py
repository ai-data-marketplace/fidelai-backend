from __future__ import annotations

from rest_framework import serializers

from apps.datasets.models.dataset import Dataset
from apps.datasets.models.assets import DatasetAsset, DatasetFileFormatChoices
from apps.datasets.models.metrics import DatasetMetrics


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

    class Meta(DatasetListSerializer.Meta):
        fields = DatasetListSerializer.Meta.fields + (
            "build_config",
            "approved_by",
            "approved_at",
        )
