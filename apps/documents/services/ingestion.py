"""
Document ingestion handler service.

Owns the write-side of document submission:
  1. Validate file extension and size at the boundary.
  2. Atomically create RawDocument + DocumentFile (triggers post_save signal).
  3. Dispatch async Groq metadata validation task.

The service is intentionally thin — it does not process the file content
(that is the processing app's responsibility).
"""
from __future__ import annotations

import hashlib
import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.documents.models import (
    DataTypeChoices,
    DocumentFile,
    DomainChoices,
    RawDocument,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "docx", "txt"})
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB

MIME_TYPE_MAP: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DocumentIngestionHandlerService:
    """
    Orchestrates the creation of a RawDocument and its associated DocumentFile.

    Usage::

        service = DocumentIngestionHandlerService()
        raw_doc = service.handle(uploaded_file=request.FILES["file"],
                                 user=request.user,
                                 metadata=serializer.validated_data)
    """

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle(self, uploaded_file, user, metadata: dict) -> RawDocument:
        """
        Validate, persist, and hand off for async processing.

        Parameters
        ----------
        uploaded_file: Django InMemoryUploadedFile / TemporaryUploadedFile
        user:          Authenticated CustomUser instance
        metadata:      Validated data dict from DocumentSubmitSerializer

        Returns the newly-created RawDocument.
        """
        extension = self._validate_file(uploaded_file)
        checksum = self._compute_checksum(uploaded_file)

        with transaction.atomic():
            raw_document = self._create_raw_document(user, metadata)
            self._create_document_file(raw_document, uploaded_file, extension, checksum)

        # Async metadata validation (Groq) — dispatched after the DB commit.
        self._dispatch_metadata_validation(raw_document)

        return raw_document

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_file(self, uploaded_file) -> str:
        """Return the lowercase extension or raise ValidationError."""
        name: str = uploaded_file.name or ""
        if "." not in name:
            raise ValidationError("Uploaded file must have an extension.")

        extension = name.rsplit(".", 1)[-1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file type '{extension}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
            )

        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                f"File size ({uploaded_file.size} bytes) exceeds the 50 MB limit."
            )

        return extension

    @staticmethod
    def _compute_checksum(uploaded_file) -> str:
        """Compute SHA-256 checksum; resets file pointer afterwards."""
        digest = hashlib.sha256()
        uploaded_file.seek(0)
        for chunk in uploaded_file.chunks(chunk_size=8192):
            digest.update(chunk)
        uploaded_file.seek(0)
        return digest.hexdigest()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_raw_document(user, metadata: dict) -> RawDocument:
        return RawDocument.objects.create(
            user=user,
            title=metadata["title"],
            description=metadata.get("description", ""),
            domain=metadata.get("domain", DomainChoices.OTHER),
            subdomain=metadata.get("subdomain", ""),
            language=metadata.get("language", "amharic"),
            data_type=DataTypeChoices.TEXT,
            consent_given=metadata.get("consent_given", False),
        )

    @staticmethod
    def _create_document_file(
        raw_document: RawDocument,
        uploaded_file,
        extension: str,
        checksum: str,
    ) -> DocumentFile:
        """
        Persisting this object fires the post_save signal which dispatches
        DocumentProcessingPipeline automatically.
        """
        file_type = MIME_TYPE_MAP.get(extension, "application/octet-stream")
        return DocumentFile.objects.create(
            raw_document=raw_document,
            file=uploaded_file,
            file_name=uploaded_file.name,
            file_type=file_type,
            file_size=uploaded_file.size,
            checksum=checksum,
        )

    # ------------------------------------------------------------------
    # Async dispatch
    # ------------------------------------------------------------------

    @staticmethod
    def _dispatch_metadata_validation(raw_document: RawDocument) -> None:
        """
        Dispatch Groq validation in a fire-and-forget manner.
        Import is deferred to avoid circular imports at module load time.
        """
        try:
            from apps.documents.tasks import ValidateDocumentMetadataTask  # noqa: PLC0415
            ValidateDocumentMetadataTask.delay(str(raw_document.pk))
        except Exception as exc:  # noqa: BLE001
            # Non-fatal: validation failure should never block the ingestion response.
            logger.warning(
                "Failed to dispatch ValidateDocumentMetadataTask for %s: %s",
                raw_document.pk,
                exc,
            )
