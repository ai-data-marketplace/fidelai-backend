import logging
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.documents.models import DomainChoices
from apps.processing.models.chunk import Chunk, ChunkStatusChoices
from apps.processing.models.expert_review import ExpertTask, ExpertTaskChunk

logger = logging.getLogger(__name__)


class ExpertTaskCreationService:
    MAX_CHUNKS_PER_EXPERT_TASK = 10

    def get_eligible_chunks_queryset(self):
        return (
            Chunk.objects.filter(
                status=ChunkStatusChoices.ESCALATED,
                consensus__requires_expert_review=True,
                expert_task_links__isnull=True,
            )
            .select_related("extracted_document__raw_document")
            .prefetch_related("consensus")
            .distinct()
            .order_by("extracted_document__raw_document__domain", "order_index", "id")
        )

    def group_chunks_by_domain(self, chunks):
        grouped_chunks = defaultdict(list)
        for chunk in chunks:
            domain = chunk.extracted_document.raw_document.domain or DomainChoices.GENERAL
            grouped_chunks[domain].append(chunk)
        return dict(grouped_chunks)

    def build_expert_task_name(self, domain, batch_number):
        domain_label = str(domain).replace("_", " ").title()
        batch_stamp = timezone.now().strftime("%Y%m%d")
        return f"Expert Review Task - {domain_label} - Batch {batch_stamp}-{batch_number:02d}"

    def link_chunks_to_expert_task(self, task, chunks):
        task_chunks = [
            ExpertTaskChunk(
                expert_task=task,
                chunk=chunk,
            )
            for chunk in chunks
        ]
        ExpertTaskChunk.objects.bulk_create(task_chunks)

        task.total_chunks = len(task_chunks)
        task.save(update_fields=["total_chunks"])

        return len(task_chunks)

    def create_expert_tasks_from_escalated_chunks(self, max_chunks_per_task=None, chunk_limit=None):
        max_chunks_per_task = max_chunks_per_task or self.MAX_CHUNKS_PER_EXPERT_TASK
        eligible_queryset = self.get_eligible_chunks_queryset()
        total_eligible_chunks = eligible_queryset.count()
        if chunk_limit is not None:
            eligible_queryset = eligible_queryset[:chunk_limit]

        eligible_chunks = list(eligible_queryset)

        summary = {
            "total_escalated_chunks_found": total_eligible_chunks,
            "chunks_scanned": len(eligible_chunks),
            "tasks_created": 0,
            "chunks_linked": 0,
            "domains_processed": [],
            "errors": 0,
            "skipped_already_linked": 0,
        }

        if not eligible_chunks:
            logger.info("No escalated chunks were eligible for expert task creation")
            return summary

        grouped_chunks = self.group_chunks_by_domain(eligible_chunks)

        for domain in sorted(grouped_chunks.keys()):
            domain_chunks = grouped_chunks[domain]
            summary["domains_processed"].append(domain)

            for batch_offset, start_index in enumerate(range(0, len(domain_chunks), max_chunks_per_task), start=1):
                batch_chunks = domain_chunks[start_index : start_index + max_chunks_per_task]

                try:
                    with transaction.atomic():
                        locked_chunks = list(
                            Chunk.objects.select_for_update()
                            .select_related("extracted_document__raw_document")
                            .prefetch_related("consensus")
                            .filter(
                                pk__in=[chunk.pk for chunk in batch_chunks],
                                status=ChunkStatusChoices.ESCALATED,
                                consensus__requires_expert_review=True,
                            )
                            .distinct()
                        )

                        fresh_chunks = [chunk for chunk in locked_chunks if not chunk.expert_task_links.exists()]
                        skipped_count = len(batch_chunks) - len(fresh_chunks)
                        summary["skipped_already_linked"] += max(skipped_count, 0)
                        if not fresh_chunks:
                            continue

                        task = ExpertTask.objects.create(
                            name=self.build_expert_task_name(domain, batch_offset),
                            domain=domain,
                            total_chunks=len(fresh_chunks),
                            created_from_consensus=True,
                        )

                        linked_count = self.link_chunks_to_expert_task(task, fresh_chunks)

                    summary["tasks_created"] += 1
                    summary["chunks_linked"] += linked_count
                    logger.info(
                        "Created expert task id=%s domain=%s linked_chunks=%s",
                        task.id,
                        domain,
                        linked_count,
                    )
                except Exception:
                    summary["errors"] += 1
                    logger.exception(
                        "Failed creating expert task for domain=%s batch=%s",
                        domain,
                        batch_offset,
                    )

        logger.info(
            "Expert task creation complete: escalated=%s scanned=%s tasks_created=%s chunks_linked=%s domains=%s errors=%s skipped_already_linked=%s",
            summary["total_escalated_chunks_found"],
            summary["chunks_scanned"],
            summary["tasks_created"],
            summary["chunks_linked"],
            len(summary["domains_processed"]),
            summary["errors"],
            summary["skipped_already_linked"],
        )
        return summary
