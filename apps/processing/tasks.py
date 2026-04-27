from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import DatabaseError, OperationalError

from apps.documents.models import RawDocument

from .services.pipeline import DocumentProcessingPipelineService


class DocumentProcessingError(Exception):
    pass


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(OperationalError, DatabaseError, OSError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def DocumentProcessingPipeline(self, raw_document_id: int):
    try:
        raw_document = RawDocument.objects.prefetch_related("files").get(pk=raw_document_id)
        return DocumentProcessingPipelineService().run(raw_document).pk
    except RawDocument.DoesNotExist as exc:
        raise DocumentProcessingError(f"RawDocument {raw_document_id} does not exist") from exc
    except ValidationError as exc:
        raise DocumentProcessingError(str(exc)) from exc
    except (OperationalError, DatabaseError) as exc:
        raise self.retry(exc=exc)