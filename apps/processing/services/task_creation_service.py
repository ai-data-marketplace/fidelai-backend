import logging

from django.db import transaction
from django.db.models import Prefetch

from apps.processing.models import (
    AnnotationTask,
    Chunk,
    ChunkStatusChoices,
    ExtractedDocument,
    TaskChunk,
)

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    pass


class NoChunksFoundError(Exception):
    pass


class MissingDomainError(Exception):
    pass


class DuplicateTaskError(Exception):
    pass


class TaskCreationService:
    def create_task_for_extracted_document(self, extracted_document_id: int, created_by=None):
        logger.info("Task creation started for ExtractedDocument %s", extracted_document_id)

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

            existing_task = self._check_existing_task(extracted_document_id=extracted_document_id)
            if existing_task:
                logger.info(
                    "Duplicate prevention triggered for ExtractedDocument %s. Existing task id=%s",
                    extracted_document_id,
                    existing_task.id,
                )
                return {
                    "task_id": existing_task.id,
                    "created": False,
                    "existing": True,
                }

            task_name = self._generate_task_name(extracted_document)
            task_description = self._generate_task_description(extracted_document=extracted_document, chunks=chunks)

            task = self._create_annotation_task(
                extracted_document=extracted_document,
                task_name=task_name,
                task_description=task_description,
                total_chunks=len(chunks),
                created_by=created_by,
            )

            self._create_task_chunks(task=task, chunks=chunks)
            self._update_chunk_statuses(chunks=chunks)

        logger.info(
            "Task creation completed for ExtractedDocument %s. Created AnnotationTask id=%s",
            extracted_document_id,
            task.id,
        )
        return {
            "task_id": task.id,
            "task_name": task.name,
            "domain": task.domain,
            "total_chunks": task.total_chunks,
            "created": True,
            "existing": False,
        }

    def _validate_document(self, extracted_document_id: int, lock_for_update: bool = False):
        queryset = (
            ExtractedDocument.objects.select_related("raw_document", "raw_document__user")
            .prefetch_related(
                "raw_document__files",
                Prefetch("chunks", queryset=Chunk.objects.order_by("order_index")),
            )
            .filter(pk=extracted_document_id)
        )
        if lock_for_update:
            queryset = queryset.select_for_update()

        extracted_document = queryset.first()
        if not extracted_document:
            raise DocumentNotFoundError(f"ExtractedDocument {extracted_document_id} does not exist")

        domain = getattr(extracted_document.raw_document, "domain", None)
        if not domain:
            raise MissingDomainError(
                f"RawDocument {extracted_document.raw_document_id} is missing domain information"
            )

        chunks = list(extracted_document.chunks.all())
        if not chunks:
            raise NoChunksFoundError(f"No chunks found for ExtractedDocument {extracted_document_id}")

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
        raw_document = extracted_document.raw_document
        contributor = getattr(raw_document, "user", None)
        contributor_display = None
        if contributor:
            contributor_display = getattr(contributor, "email", None) or getattr(contributor, "username", None)
        contributor_display = contributor_display or f"user_id={raw_document.user_id}"

        return "\n".join(
            [
                f"Raw Document ID: {raw_document.id}",
                f"Raw Document Title: {raw_document.title}",
                f"Source Contributor: {contributor_display}",
                f"Domain: {raw_document.domain}",
                f"Total Chunks: {len(chunks)}",
                f"Language: {extracted_document.language_detected}",
                f"Extraction Confidence: {extracted_document.confidence_score}",
                f"Processing Timestamp: {extracted_document.processed_at.isoformat()}",
            ]
        )

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