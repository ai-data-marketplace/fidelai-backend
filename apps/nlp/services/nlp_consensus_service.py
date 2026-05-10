"""NLP consensus computation service.

Converts multiple `NLPAnnotation` rows for a given `NLPChunk` into a single
`NLPConsensus` result using task-type aware aggregation logic.

Design goals:
- Batch processing with iterator() to avoid memory bloat
- Idempotent by default (skip chunks with existing consensus unless forced)
- Transaction safe when writing consensus and updating chunk status
- Task-type pluggable methods for SENTIMENT / NER / TOPIC_CLASSIFICATION
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Dict, Iterable, List, Optional, Set, Tuple

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Prefetch

from apps.nlp.models.nlp_consensus import NLPConsensus
from apps.nlp.models.nlp_annotation import NLPAnnotation
from apps.nlp.models.nlp_chunk import NLPChunk
from apps.nlp.models.choices import (
    NLPTaskTypeChoices,
    NLPChunkStatusChoices,
)

logger = logging.getLogger(__name__)

APPROVAL_THRESHOLD = 0.7
MIN_ANNOTATIONS_REQUIRED = 3


@dataclass(frozen=True)
class ConsensusResult:
    final_labels: Dict
    agreement_score: float
    total_annotations: int
    requires_review: bool = False


class NLPConsensusService:
    """Compute consensus labels for NLP chunks.

    Public API:
    - run(batch_size: Optional[int]=None, force: bool=False)
    """

    def run(self, batch_size: Optional[int] = None, force: bool = False) -> Dict:
        summary = {
            "processed": 0,
            "skipped_no_annotations": 0,
            "skipped_existing_consensus": 0,
            "approved": 0,
            "rejected": 0,
        }

        chunks_qs = self.fetch_chunks_ready_for_consensus(batch_size=batch_size, force=force)

        for chunk in chunks_qs.iterator():
            annotations = list(self.get_annotations(chunk))

            if len(annotations) < MIN_ANNOTATIONS_REQUIRED:
                summary["skipped_no_annotations"] += 1
                logger.debug("Chunk %s skipped: not enough annotations (%s)", chunk.id, len(annotations))
                continue

            # Idempotency: skip if consensus exists and not forced
            if not force and hasattr(chunk, "consensus") and chunk.consensus is not None:
                summary["skipped_existing_consensus"] += 1
                logger.debug("Chunk %s skipped: consensus already exists", chunk.id)
                continue

            try:
                result = self.compute_consensus(chunk, annotations)
            except Exception as exc:
                logger.exception("Failed computing consensus for chunk %s: %s", chunk.id, exc)
                continue

            # Persist consensus and update chunk status
            try:
                with transaction.atomic():
                    self.store_consensus(chunk, result)
                    self.update_chunk_status(chunk, result)
            except IntegrityError as exc:
                logger.exception("DB error storing consensus for chunk %s: %s", chunk.id, exc)
                continue

            summary["processed"] += 1
            if result.agreement_score >= APPROVAL_THRESHOLD:
                summary["approved"] += 1
            else:
                summary["rejected"] += 1

            logger.info(
                "Processed chunk %s: agreement=%.3f annotations=%d final=%s",
                chunk.id,
                result.agreement_score,
                result.total_annotations,
                result.final_labels,
            )

        logger.info("Consensus run complete: %s", summary)
        return summary

    def fetch_chunks_ready_for_consensus(self, batch_size: Optional[int] = None, force: bool = False) -> Iterable[NLPChunk]:
        """Return queryset of NLPChunk objects ready for consensus.

        Excludes chunks with existing consensus unless `force=True`.
        Prefetches annotations to avoid N+1 queries.
        """
        annotations_qs = NLPAnnotation.objects.select_related("annotator")

        consensus_exists = Exists(NLPConsensus.objects.filter(nlp_chunk=OuterRef("pk")))

        qs = (
            NLPChunk.objects.filter(status=NLPChunkStatusChoices.CONSENSUS_READY, is_active=True)
            .annotate(total_annotations=Count("annotations"))
            .prefetch_related(Prefetch("annotations", queryset=annotations_qs))
        )

        qs = qs.filter(total_annotations__gte=MIN_ANNOTATIONS_REQUIRED)

        if not force:
            qs = qs.annotate(has_consensus=consensus_exists).filter(has_consensus=False)

        qs = qs.order_by("-created_at")

        if batch_size:
            qs = qs[:batch_size]

        return qs

    def get_annotations(self, chunk: NLPChunk) -> Iterable[NLPAnnotation]:
        # annotations were prefetched in fetch_chunks_ready_for_consensus
        return chunk.annotations.all()

    def compute_consensus(self, chunk: NLPChunk, annotations: List[NLPAnnotation]) -> ConsensusResult:
        task_type = chunk.task_type

        if task_type == NLPTaskTypeChoices.SENTIMENT:
            return self.compute_sentiment_consensus(annotations)

        if task_type == NLPTaskTypeChoices.NER:
            return self.compute_ner_consensus(annotations)

        if task_type == NLPTaskTypeChoices.TOPIC_CLASSIFICATION:
            return self.compute_classification_consensus(annotations)

        # Fallback: try classification-style majority
        return self.compute_classification_consensus(annotations)

    def compute_sentiment_consensus(self, annotations: List[NLPAnnotation]) -> ConsensusResult:
        votes = []
        confidences = []
        for ann in annotations:
            try:
                sentiment = ann.labels.get("sentiment") if isinstance(ann.labels, dict) else None
            except Exception:
                sentiment = None

            if sentiment:
                votes.append(sentiment)
                confidences.append(float(ann.confidence_score) if ann.confidence_score is not None else 0.0)

        total = len(votes)
        if total == 0:
            return ConsensusResult(final_labels={}, agreement_score=0.0, total_annotations=len(annotations), requires_review=True)

        counter = Counter(votes)
        most_common_label, count = counter.most_common(1)[0]

        # tie-break: if multiple labels share top count, choose annotator with highest confidence
        top_counts = [label for label, c in counter.items() if c == count]
        if len(top_counts) > 1:
            # pick annotation with highest confidence among those that voted for top labels
            best_label = None
            best_conf = -1.0
            for ann in annotations:
                label = ann.labels.get("sentiment") if isinstance(ann.labels, dict) else None
                conf = float(ann.confidence_score) if ann.confidence_score is not None else 0.0
                if label in top_counts and conf > best_conf:
                    best_conf = conf
                    best_label = label
            final_label = best_label or most_common_label
            count = counter[final_label]
        else:
            final_label = most_common_label

        agreement_score = count / total

        final = {"sentiment": final_label}
        return ConsensusResult(final_labels=final, agreement_score=agreement_score, total_annotations=len(annotations))

    def compute_ner_consensus(self, annotations: List[NLPAnnotation]) -> ConsensusResult:
        # Normalize entities into keys (text, label) when possible
        per_ann_entity_sets: List[Set[Tuple[str, str]]] = []
        for ann in annotations:
            entities = []
            try:
                entities = ann.labels.get("entities") if isinstance(ann.labels, dict) else []
            except Exception:
                entities = []

            normalized = set()
            for e in entities or []:
                if not isinstance(e, dict):
                    continue
                text = str(e.get("text") or e.get("mention") or "").strip()
                label = str(e.get("label") or e.get("type") or "").strip()
                if text and label:
                    normalized.add((text, label))
            per_ann_entity_sets.append(normalized)

        # Count votes for each entity key
        vote_counter: Counter = Counter()
        for s in per_ann_entity_sets:
            for key in s:
                vote_counter[key] += 1

        # Keep entities with at least 2 votes (per spec)
        kept = [ {"text": k[0], "label": k[1]} for k, v in vote_counter.items() if v >= 2 ]

        # Agreement score: average Jaccard similarity between each ann and the consensus set
        consensus_set = set((e["text"], e["label"]) for e in kept)
        jaccard_scores = []
        for s in per_ann_entity_sets:
            if not s and not consensus_set:
                jaccard_scores.append(1.0)
                continue
            inter = len(s & consensus_set)
            union = len(s | consensus_set) if len(s | consensus_set) > 0 else 1
            jaccard_scores.append(inter / union)

        agreement_score = float(sum(jaccard_scores) / len(jaccard_scores)) if jaccard_scores else 0.0

        final = {"entities": kept}
        return ConsensusResult(final_labels=final, agreement_score=agreement_score, total_annotations=len(annotations))

    def compute_classification_consensus(self, annotations: List[NLPAnnotation]) -> ConsensusResult:
        votes = []
        weight_map = []
        for ann in annotations:
            try:
                label = ann.labels.get("topic") or ann.labels.get("label") if isinstance(ann.labels, dict) else None
            except Exception:
                label = None
            if label:
                votes.append(label)
                weight_map.append(float(ann.confidence_score) if ann.confidence_score is not None else 1.0)

        total = len(votes)
        if total == 0:
            return ConsensusResult(final_labels={}, agreement_score=0.0, total_annotations=len(annotations), requires_review=True)

        # Optionally use confidence weighting
        weighted = defaultdict(float)
        for v, w in zip(votes, weight_map):
            weighted[v] += w

        final_label = max(weighted.items(), key=lambda kv: kv[1])[0]
        agreement_score = sum(1 for v in votes if v == final_label) / total

        final = {"topic": final_label}
        return ConsensusResult(final_labels=final, agreement_score=agreement_score, total_annotations=len(annotations))

    def store_consensus(self, chunk: NLPChunk, result: ConsensusResult) -> None:
        # create or update NLPConsensus for the chunk
        defaults = {
            "task_type": chunk.task_type,
            "final_labels": result.final_labels,
            "agreement_score": result.agreement_score,
            "total_annotations": result.total_annotations,
            "requires_expert_review": result.requires_review,
        }

        obj, created = NLPConsensus.objects.update_or_create(
            nlp_chunk=chunk,
            defaults=defaults,
        )

        if created:
            logger.debug("Created consensus for chunk %s", chunk.id)
        else:
            logger.debug("Updated consensus for chunk %s", chunk.id)

    def update_chunk_status(self, chunk: NLPChunk, result: ConsensusResult) -> None:
        if result.agreement_score >= APPROVAL_THRESHOLD:
            chunk.status = NLPChunkStatusChoices.APPROVED
        else:
            chunk.status = NLPChunkStatusChoices.REJECTED

        chunk.save(update_fields=["status"]) 
