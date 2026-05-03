import logging
from collections import Counter
from statistics import mean

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from apps.processing.models.annotations import Annotation
from apps.processing.models.chunk import (
    Chunk,
    ChunkStatusChoices,
    TaskAssignmentStatusChoices,
)
from apps.processing.models.consensus import Consensus

logger = logging.getLogger(__name__)

MIN_ANNOTATIONS = 3
AGREEMENT_THRESHOLD = 0.75


class ConsensusPipelineService:
    MIN_ANNOTATIONS = MIN_ANNOTATIONS
    AGREEMENT_THRESHOLD = AGREEMENT_THRESHOLD

    def get_eligible_chunks_queryset(self):
        valid_annotation_filter = Q(
            annotations__is_skipped=False,
            annotations__task_assignment__status=TaskAssignmentStatusChoices.SUBMITTED,
        )
        valid_annotations = Annotation.objects.filter(
            is_skipped=False,
            task_assignment__status=TaskAssignmentStatusChoices.SUBMITTED,
        ).select_related("task_assignment")

        return (
            Chunk.objects.filter(consensus__isnull=True)
            .annotate(
                valid_annotations_count=Count("annotations", filter=valid_annotation_filter, distinct=True),
            )
            .filter(
                Q(status=ChunkStatusChoices.CONSENSUS_READY)
                | Q(status=ChunkStatusChoices.ANNOTATED, valid_annotations_count__gte=self.MIN_ANNOTATIONS)
            )
            .select_related("extracted_document")
            .prefetch_related(Prefetch("annotations", queryset=valid_annotations, to_attr="valid_annotations"))
        )

    @staticmethod
    def compute_majority_vote(values):
        """Return (majority_value, agreement_ratio)."""
        total = len(values)
        if total == 0:
            return None, 0.0

        counts = Counter(values)
        most_common = sorted(counts.items(), key=lambda iv: (-iv[1], str(iv[0])))
        value, count = most_common[0]
        return value, count / total

    def evaluate_chunk_consensus(self, chunk):
        annotations = getattr(chunk, "valid_annotations", None)
        if annotations is None:
            annotations = list(
                chunk.annotations.select_related("task_assignment").filter(
                    is_skipped=False,
                    task_assignment__status=TaskAssignmentStatusChoices.SUBMITTED,
                )
            )

        total = len(annotations)
        if total == 0:
            return {
                "total_annotations": 0,
                "agreement_score": 0.0,
                "requires_expert_review": False,
            }

        domain_vals = [a.domain_match for a in annotations]
        is_amharic_vals = [a.is_amharic for a in annotations]
        readability_vals = [a.readability for a in annotations]
        safety_vals = [a.safety_label for a in annotations]

        final_domain, domain_agree = self.compute_majority_vote(domain_vals)
        final_is_amharic, lang_agree = self.compute_majority_vote(is_amharic_vals)
        final_readability, read_agree = self.compute_majority_vote(readability_vals)
        final_safety_label, safety_agree = self.compute_majority_vote(safety_vals)

        agreement_score = mean([domain_agree, lang_agree, read_agree, safety_agree])
        requires_expert = agreement_score < self.AGREEMENT_THRESHOLD

        return {
            "final_domain_match": final_domain,
            "final_is_amharic": final_is_amharic,
            "final_readability": final_readability,
            "final_safety_label": final_safety_label,
            "agreement_score": agreement_score,
            "requires_expert_review": requires_expert,
            "total_annotations": total,
        }

    def update_chunk_status(self, chunk, result):
        agreement = result.get("agreement_score", 0.0)
        if agreement >= self.AGREEMENT_THRESHOLD and not result.get("requires_expert_review", False):
            chunk.status = ChunkStatusChoices.APPROVED
            chunk.quality_score = agreement
        else:
            chunk.status = ChunkStatusChoices.ESCALATED

        chunk.save(update_fields=["status", "quality_score"])

    def run_pipeline(self, batch_size=200):
        processed = 0
        approved = 0
        escalated = 0
        skipped_existing = 0
        agreements = []

        for chunk in self.get_eligible_chunks_queryset().iterator(chunk_size=batch_size):
            try:
                result = self.evaluate_chunk_consensus(chunk)

                with transaction.atomic():
                    chunk_for_update = Chunk.objects.select_for_update().get(pk=chunk.pk)
                    if Consensus.objects.filter(chunk=chunk_for_update).exists():
                        skipped_existing += 1
                        continue

                    Consensus.objects.create(
                        chunk=chunk_for_update,
                        final_domain_match=result.get("final_domain_match") or "uncertain",
                        final_is_amharic=bool(result.get("final_is_amharic", False)),
                        final_readability=result.get("final_readability") or "medium",
                        final_safety_label=result.get("final_safety_label") or "safe",
                        agreement_score=result.get("agreement_score", 0.0),
                        requires_expert_review=result.get("requires_expert_review", False),
                        total_annotations=result.get("total_annotations", 0),
                        computed_at=timezone.now(),
                    )

                    self.update_chunk_status(chunk_for_update, result)

            except Exception:
                logger.exception("Error processing consensus for chunk %s", chunk.id)
                continue

            processed += 1
            score = result.get("agreement_score", 0.0)
            agreements.append(score)
            if score >= self.AGREEMENT_THRESHOLD:
                approved += 1
            else:
                escalated += 1

            if processed % batch_size == 0:
                logger.info("Processed %s chunks so far in consensus pipeline", processed)

        avg_agreement = mean(agreements) if agreements else 0.0
        logger.info(
            "Consensus pipeline complete: processed=%s approved=%s escalated=%s skipped_existing=%s avg_agreement=%.3f",
            processed,
            approved,
            escalated,
            skipped_existing,
            avg_agreement,
        )

        return {
            "processed": processed,
            "approved": approved,
            "escalated": escalated,
            "skipped_existing": skipped_existing,
            "avg_agreement": avg_agreement,
        }


def compute_majority_vote(values):
    return ConsensusPipelineService.compute_majority_vote(values)


def evaluate_chunk_consensus(chunk):
    return ConsensusPipelineService().evaluate_chunk_consensus(chunk)


def update_chunk_status(chunk, result):
    return ConsensusPipelineService().update_chunk_status(chunk, result)


def run_consensus_pipeline(batch_size=200):
    return ConsensusPipelineService().run_pipeline(batch_size=batch_size)
