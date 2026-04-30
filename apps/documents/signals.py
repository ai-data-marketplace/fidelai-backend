"""
Django signals for the documents app.

Event: post_save on DocumentFile (created=True)
  → Immediately dispatches DocumentProcessingPipeline to the Celery worker.

This transitions the system from a "batch sweep" model (crontab every minute)
to an "instant event" model.  The periodic beat task remains as a safety net
for any documents that slip through (e.g. worker was down at upload time).
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.documents.models import DocumentFile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=DocumentFile)
def dispatch_processing_on_file_upload(
    sender,
    instance: DocumentFile,
    created: bool,
    **kwargs,
) -> None:
    """
    Fire-and-forget: queue the processing pipeline as soon as a new
    DocumentFile row is committed to the database.

    Only fires on creation (not on subsequent saves such as checksum updates)
    to prevent duplicate task submissions.
    """
    if not created:
        return

    raw_document_id = str(instance.raw_document_id)

    try:
        # Import deferred to avoid circular dependencies at module load time.
        from apps.processing.tasks import DocumentProcessingPipeline  # noqa: PLC0415
        DocumentProcessingPipeline.delay(raw_document_id)
        logger.info(
            "Dispatched DocumentProcessingPipeline for RawDocument %s",
            raw_document_id,
        )
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: the periodic beat task will pick it up on its next run.
        logger.warning(
            "Failed to dispatch DocumentProcessingPipeline for RawDocument %s: %s",
            raw_document_id,
            exc,
        )
