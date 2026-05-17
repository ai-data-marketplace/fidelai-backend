from __future__ import annotations

import logging
from typing import Iterable

from celery import shared_task
from django.contrib.auth import get_user_model

from apps.datasets.services.aggregation_service import DatasetAggregationService


logger = logging.getLogger(__name__)


def _parse_domains(domains: str | Iterable[str] | None) -> list[str]:
    if domains is None:
        return []
    if isinstance(domains, str):
        return [domain.strip() for domain in domains.split(",") if domain.strip()]
    return [str(domain).strip() for domain in domains if str(domain).strip()]


@shared_task
def DispatchDatasetAggregation(
    task_type: str | None = None,
    domains: str | list[str] | None = None,
    min_agreement_score: float = 0.8,
    max_examples: int | None = None,
    balance_labels: bool = True,
    created_by_id: int | None = None,
    license_type: str = "mit",
    price: float = 1000.0,
    title: str | None = None,
    description: str | None = None,
) -> dict:
    """Build a reproducible dataset from approved NLP consensus rows."""
    service = DatasetAggregationService()
    parsed_domains = _parse_domains(domains)
    created_by = None
    if created_by_id is not None:
        created_by = get_user_model().objects.filter(pk=created_by_id).first()

    logger.info(
        "Starting dataset aggregation task task_type=%s domains=%s min_agreement_score=%s max_examples=%s balance_labels=%s price=%s",
        task_type,
        parsed_domains,
        min_agreement_score,
        max_examples,
        balance_labels,
        price,
    )
    dataset = service.build_dataset(
        title=title,
        description=description,
        task_type=task_type,
        domains=parsed_domains,
        min_agreement_score=min_agreement_score,
        max_examples=max_examples,
        balance_labels=balance_labels,
        created_by=created_by,
        license_type=license_type,
        price=price,
    )

    result = {
        "queued": False,
        "dataset_id": str(dataset.pk),
        "title": dataset.title,
        "description": dataset.description,
        "task_type": dataset.nlp_task_type,
        "asset_count": dataset.assets.count(),
        "chunk_count": dataset.dataset_chunks.count(),
    }
    logger.info("Dataset aggregation completed: %s", result)
    return result