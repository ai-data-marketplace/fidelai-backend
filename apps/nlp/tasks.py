from __future__ import annotations

import logging

from celery import shared_task

from apps.nlp.services.candidate_extraction_service import CandidateExtractionService
from apps.nlp.services.nlp_task_creation_service import NLPTaskCreationService
from apps.nlp.services.nlp_task_assignment_service import NLPTaskAssignmentService
from apps.nlp.services.nlp_consensus_service import NLPConsensusService


logger = logging.getLogger(__name__)


@shared_task
def DispatchPendingNlpCandidateExtraction(batch_size: int = 50) -> dict:
    service = CandidateExtractionService()
    logger.info("Starting NLP candidate extraction with batch_size=%s", batch_size)
    service.process_approved_chunks(batch_size=batch_size)

    return {
        "queued": True,
        "batch_size": batch_size,
    }


@shared_task
def DispatchNlpTaskCreation() -> dict:
    service = NLPTaskCreationService()
    logger.info("Starting NLP task creation")
    summary = service.create_tasks()
    logger.info("NLP task creation completed: %s", summary)

    return summary


@shared_task
def DispatchNlpTaskAssignment() -> dict:
    service = NLPTaskAssignmentService()
    logger.info("Starting NLP task assignment")
    summary = service.assign_tasks()
    logger.info("NLP task assignment completed: %s", summary)

    return summary


@shared_task
def DispatchNlpConsensus(batch_size: int = 100, force: bool = False) -> dict:
    service = NLPConsensusService()
    logger.info("Starting NLP consensus run with batch_size=%s force=%s", batch_size, force)
    summary = service.run(batch_size=batch_size, force=force)
    logger.info("NLP consensus completed: %s", summary)

    return summary