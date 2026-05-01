import logging

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.core.exceptions import ValidationError
from django.db import DatabaseError, OperationalError

from apps.documents.models import ProcessingStatusChoices, RawDocument
from apps.processing.models import Chunk, ExtractedDocument

from .services.pipeline import DocumentProcessingPipelineService
from .services.chunking import DocumentChunkingPipelineService
from .services.task_creation_service import (
    DocumentNotFoundError,
    MissingDomainError,
    NoChunksFoundError,
    TaskCreationService,
)


logger = logging.getLogger(__name__)


class DocumentProcessingError(Exception):
    pass


class DocumentChunkingError(Exception):
    pass


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def CreateAnnotationTaskFromExtractedDocument(
    self,
    extracted_document_id: str,
    created_by_id: int | None = None,
    max_chunks_per_task: int = 30,
):
    try:
        result = TaskCreationService().create_task_for_extracted_document(
            extracted_document_id=extracted_document_id,
            created_by=created_by_id,
            max_chunks_per_task=max_chunks_per_task,
        )
        logger.info(
            "Task creation completed for ExtractedDocument %s: created=%s existing=%s task_id=%s",
            extracted_document_id,
            result.get("created"),
            result.get("existing"),
            result.get("task_id"),
        )
        return result
    except (NoChunksFoundError, MissingDomainError, DocumentNotFoundError) as exc:
        logger.warning(
            "Task creation skipped for ExtractedDocument %s: %s",
            extracted_document_id,
            exc,
        )
        return {
            "created": False,
            "existing": False,
            "reason": str(exc),
        }
    except (OperationalError, DatabaseError, OSError) as exc:
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError as retry_exc:
            logger.exception(
                "Task creation retries exhausted for ExtractedDocument %s",
                extracted_document_id,
            )
            raise DocumentChunkingError(
                f"Max retries exceeded for ExtractedDocument {extracted_document_id}"
            ) from retry_exc
    except Exception as exc:
        logger.exception(
            "Task creation failed for ExtractedDocument %s",
            extracted_document_id,
        )
        raise DocumentChunkingError(str(exc)) from exc


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


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def ChunkExtractedDocument(self, extracted_document_id: str):
    """Create `Chunk` rows for an ExtractedDocument.

    Safety/idempotency:
    - If any chunks already exist for the document, do nothing and return the existing count.
    """
    extracted = ExtractedDocument.objects.filter(pk=extracted_document_id).first()
    if not extracted:
        raise DocumentChunkingError(f"ExtractedDocument {extracted_document_id} does not exist")

    existing_count = Chunk.objects.filter(extracted_document=extracted).count()
    if existing_count:
        return {
            "extracted_document_id": str(extracted.pk),
            "chunk_count": int(existing_count),
            "skipped": True,
        }

    try:
        chunks = DocumentChunkingPipelineService().chunk(extracted)
        return {
            "extracted_document_id": str(extracted.pk),
            "chunk_count": int(len(chunks)),
            "skipped": False,
        }
    except (OperationalError, DatabaseError, OSError) as exc:
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError as retry_exc:
            raise DocumentChunkingError(
                f"Max retries exceeded for ExtractedDocument {extracted_document_id}"
            ) from retry_exc
    except Exception as exc:
        raise DocumentChunkingError(str(exc)) from exc


@shared_task
def DispatchPendingChunking(batch_size: int = 25):
    """Queue chunking tasks for ExtractedDocuments that don't yet have chunks."""
    pending_ids = list(
        ExtractedDocument.objects.filter(chunks__isnull=True)
        .order_by("processed_at")
        .values_list("id", flat=True)[:batch_size]
    )

    for extracted_document_id in pending_ids:
        ChunkExtractedDocument.delay(str(extracted_document_id))

    return {
        "queued_count": len(pending_ids),
        "queued_ids": [str(extracted_document_id) for extracted_document_id in pending_ids],
    }


@shared_task
def DispatchPendingTaskCreation(batch_size: int = 25, max_chunks_per_task: int = 30):
    """Queue task-creation jobs for chunked ExtractedDocuments that do not yet have AnnotationTasks."""
    pending_ids = list(
        ExtractedDocument.objects.filter(chunks__isnull=False, annotation_tasks__isnull=True)
        .order_by("processed_at")
        .values_list("id", flat=True)[:batch_size]
    )

    for extracted_document_id in pending_ids:
        CreateAnnotationTaskFromExtractedDocument.delay(
            str(extracted_document_id),
            None,
            max_chunks_per_task,
        )

    return {
        "queued_count": len(pending_ids),
        "queued_ids": [str(extracted_document_id) for extracted_document_id in pending_ids],
    }