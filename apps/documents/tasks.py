"""
Celery tasks for the documents app.

DocumentGatekeeperTask
  - Validates file type and size.
  - Extracts text from the raw document for similarity checks.
  - Generates similarity signature.
  - Runs the SimilarityService deduplication check.
  - If duplicate -> Auto-Purge and update status.
  - If unique -> Update status and trigger DocumentProcessingPipeline.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction

from apps.documents.models import ReviewStatusChoices, ProcessingStatusChoices

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def DocumentGatekeeperTask(self, raw_document_id: str) -> dict:
    """
    Gatekeeper flow for a submitted document.
    """
    from apps.documents.models import RawDocument  # noqa: PLC0415
    from apps.documents.services.similarity import SimilarityService  # noqa: PLC0415

    logger.info("DocumentGatekeeperTask started for RawDocument ID: %s", raw_document_id)

    # 1. Load the document
    try:
        raw_document = (
            RawDocument.objects.prefetch_related("files")
            .get(pk=raw_document_id)
        )
    except RawDocument.DoesNotExist:
        logger.warning("DocumentGatekeeperTask: RawDocument %s not found.", raw_document_id)
        return {"skipped": True, "reason": "document_not_found"}

    # 2. File Type/Size Check
    file_record = raw_document.files.order_by("-uploaded_at").first()
    if not file_record:
        return {"skipped": True, "reason": "No file attached"}

    extension = file_record.file_name.rsplit(".", 1)[-1].lower() if "." in file_record.file_name else ""
    if extension not in ALLOWED_EXTENSIONS or file_record.file_size > MAX_FILE_SIZE_BYTES:
        reason = "Invalid file type or size exceeds limit."
        logger.info("Gatekeeper failed for %s: %s", raw_document_id, reason)
        RawDocument.objects.filter(pk=raw_document_id).update(
            review_status=ReviewStatusChoices.REJECTED,
            validation_notes=reason,
        )
        return {"is_valid": False, "reason": reason}

    # 3. Extract text for SimilarityService
    current_text = _extract_text_for_similarity(file_record, extension)

    if not current_text:
        # If we couldn't extract text, we might skip similarity, but let's log it.
        logger.warning("Could not extract text for similarity check on %s", raw_document_id)

    # 4. Similarity Signature & Deduplication Check
    is_duplicate = False
    duplicate_info = {}
    reason = ""
    
    if current_text:
        similarity_service = SimilarityService()
        # Generate the text signature for the document
        signature = similarity_service.generate_signature(current_text)
        logger.info("Generated similarity signature for %s with %d tokens", raw_document_id, len(signature))

        is_duplicate, duplicate_info = similarity_service.check_duplicate(raw_document, current_text)

    # 5. Soft Reject & Delayed Cleanup
    if is_duplicate:
        existing_filename = duplicate_info.get("existing_file", "Unknown")
        reason = f"Duplicate of {existing_filename} detected. This record will be purged in 5 minutes."
        logger.info("SOFT REJECT: %s - %s", raw_document_id, reason)
        
        RawDocument.objects.filter(pk=raw_document_id).update(
            review_status=ReviewStatusChoices.REJECTED,
            processing_status=ProcessingStatusChoices.FAILED,
            validation_notes=reason,
        )
        
        def _schedule_purge():
            purge_rejected_document.apply_async((str(raw_document_id),), countdown=300)
            logger.info("Scheduled purge_rejected_document for %s in 300s", raw_document_id)

        transaction.on_commit(_schedule_purge)
        
        return {
            "raw_document_id": raw_document_id,
            "is_valid": False,
            "review_status": ReviewStatusChoices.REJECTED,
            "purged": False,
            "reason": reason,
        }

    # 6. Handoff Logic: If unique, trigger processing pipeline (hands-off status)
    logger.info("Gatekeeper passed for %s. Dispatching processing pipeline without status updates.", raw_document_id)

    def _trigger_pipeline():
        try:
            from apps.processing.tasks import DocumentProcessingPipeline  # noqa: PLC0415
            DocumentProcessingPipeline.delay(str(raw_document_id))
            logger.info("Dispatched DocumentProcessingPipeline for RawDocument %s", raw_document_id)
        except Exception as exc:  # noqa: BLE001
            logger.critical("Failed to dispatch DocumentProcessingPipeline for RawDocument %s: %s", raw_document_id, exc)

    transaction.on_commit(_trigger_pipeline)

    return {
        "raw_document_id": raw_document_id,
        "is_valid": True,
        "reason": "Passed Gatekeeper",
    }


def _extract_text_for_similarity(file_record, extension) -> str:
    """
    Extract text directly from the file to check for similarity.
    """
    try:
        from apps.processing.services.docx_extractor import DOCXExtractionService
        from apps.processing.services.pdf_text_extractor import PDFExtractionService

        with file_record.file.open("rb") as file_handle:
            file_bytes = file_handle.read()

        if extension == "docx":
            extracted = DOCXExtractionService().extract(file_bytes)
            return extracted.text if extracted else ""
        elif extension == "pdf":
            pdf_result = PDFExtractionService().extract(file_bytes)
            if pdf_result:
                return "\n".join(page.text for page in pdf_result)
        else:
            return file_bytes.decode('utf-8', errors='ignore')
    except Exception as exc:
        logger.warning("Error extracting text for similarity: %s", exc)
        return ""


@shared_task
def purge_rejected_document(raw_document_id: str):
    """
    Safely delete a document previously marked as REJECTED.
    """
    from apps.documents.models import RawDocument
    try:
        raw_document = RawDocument.objects.get(pk=raw_document_id)
        if raw_document.review_status == ReviewStatusChoices.REJECTED:
            for record in raw_document.files.all():
                if record.file:
                    record.file.delete(save=False)
            raw_document.delete()
            logger.info("Successfully purged REJECTED document %s", raw_document_id)
        else:
            logger.warning("purge_rejected_document aborted: Document %s is not in REJECTED state.", raw_document_id)
    except RawDocument.DoesNotExist:
        logger.info("purge_rejected_document: Document %s already deleted.", raw_document_id)
