"""Celery tasks for the NLP app."""

from __future__ import annotations

import logging

from celery import shared_task

from apps.nlp.services.candidate_extraction_service import CandidateExtractionService


logger = logging.getLogger(__name__)


@shared_task
def DispatchPendingNlpCandidateExtraction(batch_size: int = 50) -> dict:
    """Dispatch candidate extraction across QC-approved chunks.

    This task is intentionally thin: it delegates the actual Gemini-backed
    extraction work to `CandidateExtractionService` so it can be triggered by
    Celery beat or manually from scripts/tests.
    """
    service = CandidateExtractionService()
    logger.info("Starting NLP candidate extraction with batch_size=%s", batch_size)
    service.process_approved_chunks(batch_size=batch_size)

    return {
        "queued": True,
        "batch_size": batch_size,
    }