import logging

from django.db import transaction
from django.db.models import Prefetch

from apps.processing.models import (
    AnnotationTask,
    Chunk,
    ChunkStatusChoices,
    ExtractedDocument,
    ExtractedDocumentChunkingStatusChoices,
    TaskChunk,
)

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    pass


class NoChunksFoundError(Exception):
    pass


class MissingDomainError(Exception):
    pass


class ChunkingNotCompleteError(Exception):
    pass


class DuplicateTaskError(Exception):
    pass


class TaskCreationService:
    def create_task_for_extracted_document(self, extracted_document_id: int, created_by=None, max_chunks_per_task: int = 30):
        """Create one or more AnnotationTask objects for an ExtractedDocument.

        Splits ordered chunks into batches of size <= `max_chunks_per_task` and
        creates an AnnotationTask per batch. Returns summary of created and
        existing tasks.
        """
        logger.info("Task creation started for ExtractedDocument %s", extracted_document_id)

        created_tasks = []
        existing_tasks = []

        with transaction.atomic():
            extracted_document, chunks = self._validate_document(
                extracted_document_id=extracted_document_id,
                lock_for_update=True,
            )

            logger.info(
                "Validated extracted document %s with %s chunks",
                extracted_document_id,
                len(chunks),
            )

            # Partition chunks into batches
            total_chunks = len(chunks)
            if total_chunks == 0:
                raise NoChunksFoundError(f"No chunks found for ExtractedDocument {extracted_document_id}")

            parts = (total_chunks + max_chunks_per_task - 1) // max_chunks_per_task

            for part_index in range(parts):
                start = part_index * max_chunks_per_task
                end = start + max_chunks_per_task
                batch_chunks = chunks[start:end]

                # Duplicate prevention: skip if any task already links to these chunks
                batch_chunk_ids = [c.id for c in batch_chunks]
                existing = (
                    AnnotationTask.objects.filter(extracted_document=extracted_document)
                    .filter(task_chunks__chunk__id__in=batch_chunk_ids)
                    .distinct()
                    .first()
                )

                if existing:
                    logger.info(
                        "Skipping creation for part %s/%s because existing AnnotationTask id=%s links to these chunks",
                        part_index + 1,
                        parts,
                        existing.id,
                    )
                    existing_tasks.append({"task_id": existing.id, "part": part_index + 1})
                    continue

                # Create task for this batch
                task_name = self._generate_task_name(extracted_document)
                # append part info to name when multiple parts
                if parts > 1:
                    task_name = f"{task_name} (Part {part_index + 1}/{parts})"

                task_description = self._generate_task_description(extracted_document=extracted_document, chunks=batch_chunks)

                task = AnnotationTask.objects.create(
                    name=task_name,
                    domain=extracted_document.raw_document.domain,
                    description=task_description,
                    created_by=created_by,
                    total_chunks=len(batch_chunks),
                    extracted_document=extracted_document,
                )

                self._create_task_chunks(task=task, chunks=batch_chunks)
                # intentionally do not change chunk statuses at this stage

                created_tasks.append({"task_id": task.id, "task_name": task.name, "total_chunks": task.total_chunks, "part": part_index + 1})

        logger.info(
            "Task creation completed for ExtractedDocument %s. created=%s existing=%s",
            extracted_document_id,
            len(created_tasks),
            len(existing_tasks),
        )

        return {
            "created": bool(created_tasks),
            "created_tasks": created_tasks,
            "existing_tasks": existing_tasks,
            "total_chunks": total_chunks,
        }

    def _validate_document(self, extracted_document_id: int, lock_for_update: bool = False):
        queryset = (
            ExtractedDocument.objects.select_related("raw_document", "raw_document__user")
            .prefetch_related(
                "raw_document__files",
                Prefetch("chunks", queryset=Chunk.objects.filter(status=ChunkStatusChoices.PENDING).order_by("order_index")),
            )
            .filter(pk=extracted_document_id)
        )
        if lock_for_update:
            queryset = queryset.select_for_update()

        extracted_document = queryset.first()
        if not extracted_document:
            raise DocumentNotFoundError(f"ExtractedDocument {extracted_document_id} does not exist")

        if extracted_document.chunking_status != ExtractedDocumentChunkingStatusChoices.CHUNKED:
            raise ChunkingNotCompleteError(
                f"ExtractedDocument {extracted_document_id} has not completed chunking yet"
            )

        domain = getattr(extracted_document.raw_document, "domain", None)
        if not domain:
            raise MissingDomainError(
                f"RawDocument {extracted_document.raw_document_id} is missing domain information"
            )

        chunks = list(extracted_document.chunks.filter(status=ChunkStatusChoices.PENDING).order_by("order_index"))
        if not chunks:
            raise NoChunksFoundError(f"No pending chunks found for ExtractedDocument {extracted_document_id}")

        return extracted_document, chunks

    def _generate_task_name(self, extracted_document: ExtractedDocument):
        raw_document = extracted_document.raw_document
        domain = raw_document.domain
        base_name = (raw_document.title or "").strip()

        if not base_name:
            latest_file = raw_document.files.order_by("-uploaded_at").only("file_name").first()
            base_name = (latest_file.file_name or "").strip() if latest_file else ""

        if not base_name:
            base_name = f"Document {raw_document.id}"

        return f"{base_name} - {domain} Annotation Task"

    def _generate_task_description(self, extracted_document: ExtractedDocument, chunks: list[Chunk]):
        domain = extracted_document.raw_document.domain
        domain_phrases = {
            "health": "medical transcription segments",
            "education": "educational transcription segments",
            "law": "legal transcription segments",
            "finance": "financial transcription segments",
            "news": "news transcription segments",
            "religion": "religious transcription segments",
            "other": "transcription segments",
        }
        subject = domain_phrases.get(domain, "transcription segments")
        return f"Annotate {subject}."

    def _create_annotation_task(
        self,
        *,
        extracted_document: ExtractedDocument,
        task_name: str,
        task_description: str,
        total_chunks: int,
        created_by,
    ):
        task = AnnotationTask.objects.create(
            name=task_name,
            domain=extracted_document.raw_document.domain,
            description=task_description,
            created_by=created_by,
            total_chunks=total_chunks,
        )
        logger.info(
            "Created AnnotationTask id=%s for ExtractedDocument %s (domain=%s)",
            task.id,
            extracted_document.id,
            task.domain,
        )
        return task

    def _create_task_chunks(self, task: AnnotationTask, chunks: list[Chunk]):
        task_chunks = [
            TaskChunk(
                task=task,
                chunk=chunk,
                order_index=chunk.order_index,
            )
            for chunk in chunks
        ]
        TaskChunk.objects.bulk_create(task_chunks)
        logger.info(
            "Bulk created %s TaskChunk rows for AnnotationTask id=%s",
            len(task_chunks),
            task.id,
        )

    def _update_chunk_statuses(self, chunks: list[Chunk]):
        logger.info(
            "Chunk status update skipped by configuration. %s/%s chunks remain in %s",
            len(chunks),
            len(chunks),
            ChunkStatusChoices.PENDING,
        )

    def _check_existing_task(self, extracted_document_id: int):
        return (
            AnnotationTask.objects.filter(task_chunks__chunk__extracted_document_id=extracted_document_id)
            .distinct()
            .order_by("-created_at")
            .first()
        )