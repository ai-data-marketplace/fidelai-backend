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

from apps.documents.models import ReviewStatusChoices

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
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

    # 5. Auto-Purge
    if is_duplicate:
        purge_msg = f"PURGING DUPLICATE: [{duplicate_info['new_file']}] was {duplicate_info['score']:.2f}% similar to [{duplicate_info['existing_file']}]"
        logger.info(purge_msg)
        
        reason = "This content is too similar to an existing document and has been flagged as a duplicate."
        
        RawDocument.objects.filter(pk=raw_document_id).update(
            review_status=ReviewStatusChoices.REJECTED,
            validation_notes=reason,
        )
        
        for record in raw_document.files.all():
            if record.file:
                record.file.delete(save=False)
                
        raw_document.delete()
        
        return {
            "raw_document_id": raw_document_id,
            "is_valid": False,
            "review_status": ReviewStatusChoices.REJECTED,
            "confidence": 1.0,
            "reason": reason,
            "purged": True,
        }

    # 6. Handoff Logic: If unique, update status and trigger the processing pipeline
    logger.info("Gatekeeper passed for %s. Updating status and dispatching processing pipeline.", raw_document_id)
    
    RawDocument.objects.filter(pk=raw_document_id).update(
        review_status=ReviewStatusChoices.APPROVED,
        validation_notes="Document passed gatekeeper checks.",
    )

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
        "review_status": ReviewStatusChoices.APPROVED,
        "confidence": 1.0,
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
