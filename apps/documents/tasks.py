"""
Celery tasks for the documents app.

ValidateDocumentMetadataTask
  - Reads the RawDocument and its first DocumentFile.
  - Extracts a text preview:
      * TXT files  → read first 2000 bytes directly from storage.
      * PDF / DOCX → use ExtractedDocument.full_text once processing completes
                     (if not yet available, exits gracefully and relies on the
                     periodic beat task to retry eventually).
  - Calls the configured AbstractDocumentValidator.
  - Persists the result back to RawDocument.review_status + validation_notes.
"""
from __future__ import annotations

import logging

from celery import shared_task

from apps.documents.models import ReviewStatusChoices

logger = logging.getLogger(__name__)

_MAX_PREVIEW_BYTES = 2_000


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def ValidateDocumentMetadataTask(self, raw_document_id: str) -> dict:
    """
    Groq-backed domain/language alignment check for a submitted document.

    Returns a summary dict (for Celery result backends / logging).
    """
    from apps.documents.models import RawDocument  # noqa: PLC0415 – deferred to avoid import cycles
    from apps.documents.services.validation import get_validator  # noqa: PLC0415

    # ------------------------------------------------------------------ #
    # 1. Load the document
    # ------------------------------------------------------------------ #
    try:
        raw_document = (
            RawDocument.objects.prefetch_related("files")
            .select_related("extracted_document")
            .get(pk=raw_document_id)
        )
    except RawDocument.DoesNotExist:
        logger.warning("ValidateDocumentMetadataTask: RawDocument %s not found.", raw_document_id)
        return {"skipped": True, "reason": "document_not_found"}

    # ------------------------------------------------------------------ #
    # 2. Extract a text preview
    # ------------------------------------------------------------------ #
    preview = _extract_text_preview(raw_document)

    if preview is None:
        # Processing not yet done for non-TXT files — reschedule once.
        logger.info(
            "ValidateDocumentMetadataTask: ExtractedDocument not ready for %s, will retry.",
            raw_document_id,
        )
        try:
            raise self.retry(countdown=120)
        except Exception:  # MaxRetriesExceededError
            logger.warning(
                "ValidateDocumentMetadataTask: gave up waiting for extraction on %s.",
                raw_document_id,
            )
            return {"skipped": True, "reason": "extraction_not_ready"}

    # ------------------------------------------------------------------ #
    # 3. Run validation
    # ------------------------------------------------------------------ #
    try:
        validator = get_validator()
        result = validator.validate(
            text=preview,
            domain=raw_document.domain,
            language=raw_document.language,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Validator init/call failed for %s: %s", raw_document_id, exc)
        return {"skipped": True, "reason": f"validator_error: {exc}"}

    # ------------------------------------------------------------------ #
    # 4. Persist outcome
    # ------------------------------------------------------------------ #
    new_review_status = (
        ReviewStatusChoices.APPROVED if result.is_valid else ReviewStatusChoices.REJECTED
    )
    RawDocument.objects.filter(pk=raw_document_id).update(
        review_status=new_review_status,
        validation_notes=result.reason,
    )

    logger.info(
        "ValidateDocumentMetadataTask: document=%s is_valid=%s confidence=%.2f",
        raw_document_id,
        result.is_valid,
        result.confidence,
    )

    return {
        "raw_document_id": raw_document_id,
        "is_valid": result.is_valid,
        "review_status": new_review_status,
        "confidence": result.confidence,
        "reason": result.reason,
    }


# ---------------------------------------------------------------------------
# Helper: text preview extraction
# ---------------------------------------------------------------------------


def _extract_text_preview(raw_document) -> str | None:
    """
    Return up to _MAX_PREVIEW_BYTES of text for validation.

    Strategy:
      - TXT files: open the file from storage and read directly.
      - PDF / DOCX: use the already-extracted full_text from the processing pipeline.
      - If no text is available yet, return None (caller will retry).
    """
    file_record = raw_document.files.order_by("-uploaded_at").first()
    if not file_record:
        return ""  # No file at all — validate with empty string (will fail is_valid).

    file_name: str = file_record.file_name or ""
    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    if extension == "txt":
        try:
            with file_record.file.open("rb") as fh:
                raw_bytes = fh.read(_MAX_PREVIEW_BYTES)
            return raw_bytes.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read TXT preview for %s: %s", raw_document.pk, exc)
            return ""

    # For PDF / DOCX wait for ExtractedDocument
    try:
        extracted = raw_document.extracted_document
        if extracted and extracted.full_text:
            return extracted.full_text[:_MAX_PREVIEW_BYTES]
    except Exception:  # noqa: BLE001
        pass

    return None  # Signal to caller: not ready yet
