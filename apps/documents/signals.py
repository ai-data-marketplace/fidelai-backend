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
    logger.info("post_save signal triggered for DocumentFile, raw_document_id: %s", raw_document_id)

    def _dispatch_pipeline():
        logger.info("Entering on_commit hook for DocumentGatekeeperTask dispatch, raw_document_id: %s", raw_document_id)
        try:
            from apps.documents.tasks import DocumentGatekeeperTask  # noqa: PLC0415
            DocumentGatekeeperTask.delay(raw_document_id)
            logger.info(
                "Dispatched DocumentGatekeeperTask for RawDocument %s",
                raw_document_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.critical(
                "CRITICAL: Broker unreachable. Failed to dispatch DocumentGatekeeperTask for RawDocument %s: %s",
                raw_document_id,
                exc,
                exc_info=True,
            )
            from apps.documents.models import RawDocument, ReviewStatusChoices
            RawDocument.objects.filter(pk=raw_document_id).update(
                review_status=ReviewStatusChoices.REJECTED
            )

    from django.db import transaction
    transaction.on_commit(_dispatch_pipeline)
