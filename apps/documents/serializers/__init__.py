"""
Serializers for the documents app.

DocumentSubmitSerializer      — validates multipart upload input (write side)
DocumentFileSerializer        — read-only representation of a DocumentFile
RawDocumentListSerializer     — lightweight list representation
RawDocumentDetailSerializer   — full detail including nested files
"""
from __future__ import annotations

from rest_framework import serializers

from apps.documents.models import (
    DocumentFile,
    DomainChoices,
    RawDocument,
)


class DocumentSubmitSerializer(serializers.Serializer):
    """
    Write-side serializer for the multipart document submission endpoint.
    The `file` field accepts a raw uploaded file object.
    """

    file = serializers.FileField(
        help_text="The document to upload (PDF, DOCX, or TXT). Max 50 MB."
    )
    title = serializers.CharField(max_length=255, help_text="Human-readable title for the dataset.")
    description = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="Optional description."
    )
    domain = serializers.ChoiceField(
        choices=DomainChoices.choices,
        default=DomainChoices.OTHER,
        help_text="Content domain (health, law, education, etc.).",
    )
    subdomain = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=100
    )
    language = serializers.CharField(
        required=False, default="amharic", max_length=50,
        help_text="Primary language of the document (default: amharic)."
    )
    consent_given = serializers.BooleanField(
        default=False,
        help_text="Contributor confirms they have rights to submit this data."
    )


class DocumentFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentFile
        fields = ["id", "file_name", "file_type", "file_size", "checksum", "uploaded_at"]
        read_only_fields = fields


class RawDocumentListSerializer(serializers.ModelSerializer):
    """Lightweight representation for list views."""

    class Meta:
        model = RawDocument
        fields = [
            "id",
            "title",
            "domain",
            "language",
            "processing_status",
            "review_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RawDocumentDetailSerializer(serializers.ModelSerializer):
    """Full detail including nested files and validation notes."""

    files = DocumentFileSerializer(many=True, read_only=True)

    class Meta:
        model = RawDocument
        fields = [
            "id",
            "title",
            "description",
            "domain",
            "subdomain",
            "language",
            "data_type",
            "consent_given",
            "processing_status",
            "review_status",
            "validation_notes",
            "files",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
