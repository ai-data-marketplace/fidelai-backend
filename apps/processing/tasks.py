from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.core.exceptions import ValidationError
from django.db import DatabaseError, OperationalError

from apps.documents.models import ProcessingStatusChoices, RawDocument
from apps.processing.models import ExtractedDocument

from .services.pipeline import DocumentProcessingPipelineService


class DocumentProcessingError(Exception):
    pass


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def DocumentProcessingPipeline(self, raw_document_id: int):
    claimed = RawDocument.objects.filter(
        pk=raw_document_id,
        processing_status=ProcessingStatusChoices.PENDING,
    ).update(processing_status=ProcessingStatusChoices.PROCESSING)

    if not claimed:
        raw_document = RawDocument.objects.filter(pk=raw_document_id).first()
        if not raw_document:
            raise DocumentProcessingError(f"RawDocument {raw_document_id} does not exist")

        if raw_document.processing_status == ProcessingStatusChoices.COMPLETED:
            existing = ExtractedDocument.objects.filter(raw_document_id=raw_document_id).only("pk").first()
            return str(existing.pk) if existing else None

        # Skip re-processing for documents not in pending state.
        return None

    try:
        raw_document = RawDocument.objects.prefetch_related("files").get(pk=raw_document_id)
        return str(DocumentProcessingPipelineService().run(raw_document).pk)
    except RawDocument.DoesNotExist as exc:
        raise DocumentProcessingError(f"RawDocument {raw_document_id} does not exist") from exc
    except ValidationError as exc:
        RawDocument.objects.filter(pk=raw_document_id).update(processing_status=ProcessingStatusChoices.FAILED)
        raise DocumentProcessingError(str(exc)) from exc
    except (OperationalError, DatabaseError, OSError) as exc:
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError as retry_exc:
            RawDocument.objects.filter(pk=raw_document_id).update(processing_status=ProcessingStatusChoices.FAILED)
            raise DocumentProcessingError(f"Max retries exceeded for RawDocument {raw_document_id}") from retry_exc
    except Exception as exc:
        RawDocument.objects.filter(pk=raw_document_id).update(processing_status=ProcessingStatusChoices.FAILED)
        raise DocumentProcessingError(str(exc)) from exc


@shared_task
def DispatchPendingDocumentProcessing(batch_size: int = 25):
    """Queue processing tasks for pending RawDocuments."""
    pending_ids = list(
        RawDocument.objects.filter(processing_status=ProcessingStatusChoices.PENDING)
        .order_by("created_at")
        .values_list("id", flat=True)[:batch_size]
    )

    for raw_document_id in pending_ids:
        DocumentProcessingPipeline.delay(str(raw_document_id))

    return {
        "queued_count": len(pending_ids),
        "queued_ids": [str(raw_document_id) for raw_document_id in pending_ids],
    }