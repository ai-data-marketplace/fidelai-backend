"""Service for batching NLP chunks into annotation tasks.

This service groups ready NLP chunks by task type and source domain, creates
annotation tasks in batches, links the chunks to each task, and advances chunk
status into the annotation workflow.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from itertools import islice
from typing import DefaultDict, Dict, Iterable, Iterator, List, Tuple

from django.db import transaction
from django.utils import timezone

from apps.nlp.models import NLPAnnotationTask, NLPChunk, NLPChunkStatusChoices, NLPTaskChunk


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskGroupKey:
    task_type: str
    source_domain: str


class NLPTaskCreationService:
    """Batch NLP chunks into annotation tasks."""

    MAX_CHUNKS_PER_TASK = 30
    READY_STATUSES = (NLPChunkStatusChoices.READY_FOR_ANNOTATION,)

    def create_tasks(self) -> Dict[str, object]:
        """Create annotation tasks from ready NLP chunks.

        Returns a summary of created tasks, grouped chunk counts, and skipped
        chunks. The operation is idempotent because only unassigned ready
        chunks are fetched.
        """
        summary: Dict[str, object] = {
            "tasks_created": 0,
            "task_chunks_created": 0,
            "chunks_scanned": 0,
            "chunks_skipped_already_assigned": 0,
            "chunks_skipped_not_ready": 0,
            "grouped_counts": {},
            "created_tasks": [],
        }

        with transaction.atomic():
            ready_chunks_qs = self.fetch_ready_chunks().select_for_update()
            summary["chunks_scanned"] = ready_chunks_qs.count()

            if not summary["chunks_scanned"]:
                logger.info("NLP task creation found no ready chunks")
                return summary

            grouped_chunks = self.group_chunks(ready_chunks_qs.iterator())
            summary["grouped_counts"] = {
                f"{key.task_type}:{key.source_domain}": len(chunks)
                for key, chunks in grouped_chunks.items()
            }

            created_tasks: List[Dict[str, object]] = []
            total_task_chunks_created = 0

            for group_key, chunks in grouped_chunks.items():
                existing_batch_index = self._existing_batch_count(group_key.task_type, group_key.source_domain)

                for batch_number, chunk_batch in enumerate(self._chunk_batches(chunks, self.MAX_CHUNKS_PER_TASK), start=1):
                    task = self.create_task(
                        task_type=group_key.task_type,
                        source_domain=group_key.source_domain,
                        batch_number=existing_batch_index + batch_number,
                        total_chunks=len(chunk_batch),
                    )
                    self.create_task_chunks(task, chunk_batch)
                    self.update_chunk_statuses(chunk_batch)

                    total_task_chunks_created += len(chunk_batch)
                    created_tasks.append(
                        {
                            "task_id": task.id,
                            "task_name": task.name,
                            "task_type": task.task_type,
                            "source_domain": task.domain,
                            "total_chunks": task.total_chunks,
                        }
                    )

                    logger.info(
                        "Created NLP annotation task id=%s name=%s task_type=%s domain=%s chunks=%s",
                        task.id,
                        task.name,
                        task.task_type,
                        task.domain,
                        len(chunk_batch),
                    )

            summary["tasks_created"] = len(created_tasks)
            summary["task_chunks_created"] = total_task_chunks_created
            summary["created_tasks"] = created_tasks

            logger.info(
                "NLP task creation completed: tasks_created=%s task_chunks_created=%s grouped=%s",
                summary["tasks_created"],
                summary["task_chunks_created"],
                summary["grouped_counts"],
            )

        return summary

    def fetch_ready_chunks(self):
        """Return NLP chunks ready for annotation and not already assigned."""
        return (
            NLPChunk.objects.select_related("source_chunk", "source_chunk__extracted_document")
            .filter(status__in=self.READY_STATUSES, task_assignments__isnull=True)
            .order_by("task_type", "source_domain", "created_at", "order_index", "id")
        )

    def group_chunks(self, chunks: Iterable[NLPChunk]) -> Dict[TaskGroupKey, List[NLPChunk]]:
        """Group chunks by NLP task type and source domain."""
        grouped: Dict[TaskGroupKey, List[NLPChunk]] = {}

        for chunk in chunks:
            group_key = TaskGroupKey(
                task_type=chunk.task_type,
                source_domain=self._normalize_domain(chunk.source_domain),
            )
            grouped.setdefault(group_key, []).append(chunk)

        return grouped

    def create_task(self, task_type: str, source_domain: str, batch_number: int, total_chunks: int) -> NLPAnnotationTask:
        """Create a single annotation task for one chunk batch."""
        domain_token = self._format_token(source_domain)
        task_type_token = self._format_token(task_type)
        today = timezone.localdate()

        task_name = f"{task_type_token}_{domain_token}_{today:%Y_%m_%d}_BATCH_{batch_number:03d}"
        task_description = self._build_task_description(task_type=task_type, source_domain=source_domain)

        return NLPAnnotationTask.objects.create(
            task_type=task_type,
            name=task_name,
            description=task_description,
            domain=self._normalize_domain(source_domain),
            total_chunks=total_chunks,
            is_active=True,
        )

    def create_task_chunks(self, task: NLPAnnotationTask, chunks: List[NLPChunk]) -> List[NLPTaskChunk]:
        """Create task-chunk links while preserving chunk order within the task."""
        task_chunks = [
            NLPTaskChunk(
                task=task,
                nlp_chunk=chunk,
                order_index=index,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]
        NLPTaskChunk.objects.bulk_create(task_chunks)
        return task_chunks

    def update_chunk_statuses(self, chunks: List[NLPChunk]) -> None:
        """Move chunks into the annotation workflow."""
        for chunk in chunks:
            chunk.status = NLPChunkStatusChoices.IN_ANNOTATION
        NLPChunk.objects.bulk_update(chunks, ["status"])

    def _existing_batch_count(self, task_type: str, source_domain: str) -> int:
        today = timezone.localdate()
        return (
            NLPAnnotationTask.objects.filter(
                task_type=task_type,
                domain=self._normalize_domain(source_domain),
                created_at__date=today,
            ).count()
        )

    def _chunk_batches(self, chunks: List[NLPChunk], batch_size: int) -> Iterator[List[NLPChunk]]:
        iterator = iter(chunks)
        while True:
            batch = list(islice(iterator, batch_size))
            if not batch:
                break
            yield batch

    def _build_task_description(self, task_type: str, source_domain: str) -> str:
        task_label = self._humanize_task_type(task_type)
        domain_label = self._humanize_domain(source_domain)
        return f"{task_label} annotation task for {domain_label} Amharic NLP chunks."

    def _normalize_domain(self, source_domain: str) -> str:
        domain = (source_domain or "general").strip().lower()
        return domain or "general"

    def _humanize_domain(self, source_domain: str) -> str:
        domain = self._normalize_domain(source_domain)
        return domain.replace("_", " ")

    def _humanize_task_type(self, task_type: str) -> str:
        return (task_type or "nlp").replace("_", " ").upper()

    def _format_token(self, value: str) -> str:
        token = self._normalize_domain(value)
        token = re.sub(r"[^a-z0-9]+", "_", token)
        token = token.strip("_")
        return token.upper() or "GENERAL"


__all__ = ["NLPTaskCreationService", "TaskGroupKey"]