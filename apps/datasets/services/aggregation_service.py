import hashlib
import io
import json
import re
import csv
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Optional

from django.core.files.base import ContentFile
from django.db import models
from django.db import transaction
from django.utils import timezone

from apps.datasets.models.assets import DatasetAsset, DatasetFileFormatChoices
from apps.datasets.models.chunk_map import DatasetChunk
from apps.datasets.models.dataset import Dataset, DatasetStatusChoices
from apps.datasets.models.metrics import DatasetMetrics
from apps.documents.models import DomainChoices
from apps.scoring.services import score_dataset_included
from apps.nlp.models.choices import NLPChunkStatusChoices, NLPTaskTypeChoices
from apps.nlp.models.nlp_chunk import NLPChunk

TEXT_NORMALIZE_RE = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    if text is None:
        return ""
    t = text.strip().lower()
    t = TEXT_NORMALIZE_RE.sub(" ", t)
    return t


def _hash_text(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


class DatasetAggregationService:
    """Service to build reproducible datasets from approved NLP consensuses.

    Usage:
        service = DatasetAggregationService()
        dataset = service.build_dataset(...)
    """

    @transaction.atomic
    def build_dataset(
        self,
        task_type: str | None = None,
        domains: Optional[List[str]] = None,
        min_agreement_score: float = 0.8,
        max_examples: Optional[int] = None,
        balance_labels: bool = False,
        created_by=None,
        license_type: str = "mit",
        price: float = 1000.0,
        title: str | None = None,
        description: str | None = None,
    ) -> Dataset:
        task_type = task_type or self._infer_task_type(domains=domains, min_agreement_score=min_agreement_score)
        self._validate_inputs(task_type=task_type, max_examples=max_examples)
        candidates = self._collect_candidates(
            task_type=task_type,
            domains=domains,
            min_agreement_score=min_agreement_score,
        )
        selected = self._select_examples(
            candidates=candidates,
            balance_labels=balance_labels,
            max_examples=max_examples,
        )

        build_config = self._build_config(
            task_type=task_type,
            domains=domains,
            min_agreement_score=min_agreement_score,
            balance_labels=balance_labels,
            max_examples=max_examples,
        )
        dataset = self._create_dataset(
            task_type=task_type,
            selected=selected,
            title=title,
            description=description,
            build_config=build_config,
            created_by=created_by,
            license_type=license_type,
            price=price,
        )
        self._create_dataset_chunks(dataset=dataset, selected=selected)
        metrics = self._create_metrics(dataset=dataset, selected=selected)
        self._create_export_asset(dataset=dataset, selected=selected, metrics=metrics)
        score_dataset_included(dataset)

        dataset.metrics = metrics
        return dataset

    def _infer_task_type(self, domains: Optional[List[str]], min_agreement_score: float) -> str:
        queryset = NLPChunk.objects.filter(
            status=NLPChunkStatusChoices.APPROVED,
            consensus__isnull=False,
            consensus__agreement_score__gte=min_agreement_score,
        )
        if domains:
            queryset = queryset.filter(source_domain__in=domains)

        top_task_type = (
            queryset.values("task_type")
            .annotate(total=models.Count("id"))
            .order_by("-total", "task_type")
            .first()
        )
        if not top_task_type or not top_task_type.get("task_type"):
            raise ValueError("no eligible chunks found to infer dataset task type")
        return top_task_type["task_type"]

    def _validate_inputs(self, task_type: str, max_examples: Optional[int]) -> None:
        if task_type not in [choice.value for choice in NLPTaskTypeChoices]:
            raise ValueError("invalid task type")
        if max_examples is not None and max_examples <= 0:
            raise ValueError("max_examples must be > 0")

    def _collect_candidates(
        self,
        task_type: str,
        domains: Optional[List[str]],
        min_agreement_score: float,
    ) -> list[dict]:
        queryset = self._eligible_chunk_queryset(
            task_type=task_type,
            domains=domains,
            min_agreement_score=min_agreement_score,
        )

        seen_hashes = set()
        candidates = []
        for nlp_chunk in queryset.iterator():
            candidate = self._candidate_from_chunk(nlp_chunk=nlp_chunk, task_type=task_type)
            if not candidate:
                continue
            text_hash = _hash_text(candidate["normalized_text"])
            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)
            candidates.append(candidate)

        if not candidates:
            raise ValueError("no eligible chunks found with the provided filters")
        return candidates

    def _eligible_chunk_queryset(
        self,
        task_type: str,
        domains: Optional[List[str]],
        min_agreement_score: float,
    ):
        queryset = (
            NLPChunk.objects.filter(
                status=NLPChunkStatusChoices.APPROVED,
                is_active=True,
                task_type=task_type,
                consensus__isnull=False,
                consensus__agreement_score__gte=min_agreement_score,
            )
            .select_related("consensus", "source_chunk__extracted_document__raw_document")
        )
        if domains:
            queryset = queryset.filter(source_domain__in=domains)
        return queryset

    def _candidate_from_chunk(self, nlp_chunk: NLPChunk, task_type: str) -> Optional[dict]:
        consensus = getattr(nlp_chunk, "consensus", None)
        if not consensus:
            return None

        label = self._extract_label(final_labels=consensus.final_labels, task_type=task_type)
        if not label:
            return None

        text = nlp_chunk.text or ""
        normalized_text = _normalize_text(text)
        if not normalized_text:
            return None

        return {
            "nlp_chunk": nlp_chunk,
            "label": str(label),
            "agreement": float(consensus.agreement_score),
            "normalized_text": normalized_text,
            "text_bytes": len(text.encode("utf-8")),
            "token_count": len(normalized_text.split()),
        }

    def _extract_label(self, final_labels, task_type: str):
        if not isinstance(final_labels, dict):
            return None
        if task_type in final_labels:
            return final_labels.get(task_type)
        for value in final_labels.values():
            if isinstance(value, (str, int, float)):
                return value
        return None

    def _select_examples(self, candidates: list[dict], balance_labels: bool, max_examples: Optional[int]) -> list[dict]:
        groups = defaultdict(list)
        for candidate in candidates:
            groups[candidate["label"]].append(candidate)

        if balance_labels and len(groups) < 2:
            raise ValueError("insufficient label diversity for balancing")

        if balance_labels:
            selected = self._select_balanced_examples(groups=groups, max_examples=max_examples)
        else:
            selected = self._select_unbalanced_examples(candidates=candidates, max_examples=max_examples)

        if not selected:
            raise ValueError("no examples selected after applying balancing/max limits")
        return selected

    def _select_balanced_examples(self, groups: dict, max_examples: Optional[int]) -> list[dict]:
        labels = list(groups.keys())
        per_label_limit = min(len(group) for group in groups.values())
        if max_examples:
            per_label_limit = min(per_label_limit, max_examples // len(labels))
        if per_label_limit <= 0:
            raise ValueError("max_examples too small for requested balancing")

        selected = []
        for label in labels:
            ranked_group = sorted(groups[label], key=lambda item: (-item["agreement"], item["nlp_chunk"].id))
            selected.extend(ranked_group[:per_label_limit])

        if max_examples and len(selected) > max_examples:
            return selected[:max_examples]
        return selected

    def _select_unbalanced_examples(self, candidates: list[dict], max_examples: Optional[int]) -> list[dict]:
        selected = sorted(candidates, key=lambda item: (-item["agreement"], item["nlp_chunk"].id))
        if max_examples:
            selected = selected[:max_examples]
        return selected

    def _build_config(
        self,
        task_type: str,
        domains: Optional[List[str]],
        min_agreement_score: float,
        balance_labels: bool,
        max_examples: Optional[int],
    ) -> dict:
        return {
            "task_type": task_type,
            "domains": domains or [],
            "min_agreement_score": min_agreement_score,
            "balanced_labels": bool(balance_labels),
            "max_examples": max_examples,
        }

    def _create_dataset(
        self,
        task_type: str,
        selected: list[dict],
        title: str | None,
        description: str | None,
        build_config: dict,
        created_by,
        license_type: str,
        price: float,
    ) -> Dataset:
        dataset_domain = self._resolve_dataset_domain(selected=selected)
        dataset_title = title or self._build_dataset_title(task_type=task_type, selected=selected)
        dataset_description = description or self._build_dataset_description(task_type=task_type, selected=selected)
        return Dataset.objects.create(
            title=dataset_title,
            description=dataset_description,
            domain=dataset_domain,
            subdomain=self._resolve_dataset_subdomain(selected=selected),
            language="amharic",
            license_type=license_type,
            price=price,
            version="v1.0",
            status=DatasetStatusChoices.APPROVED,
            collection_year=datetime.utcnow().year,
            created_by=created_by,
            nlp_task_type=task_type,
            build_config=build_config,
        )

    def _resolve_dataset_domain(self, selected: list[dict]) -> str:
        domain_counts = Counter(item["nlp_chunk"].source_domain or DomainChoices.GENERAL for item in selected)
        if not domain_counts:
            return DomainChoices.GENERAL
        return sorted(domain_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    def _resolve_dataset_subdomain(self, selected: list[dict]) -> str:
        domains = sorted({item["nlp_chunk"].source_domain or DomainChoices.GENERAL for item in selected})
        if len(domains) <= 1:
            return domains[0] if domains else ""
        return ", ".join(domains)

    def _build_dataset_title(self, task_type: str, selected: list[dict]) -> str:
        domain = self._resolve_dataset_domain(selected=selected)
        task_label = task_type.replace("_", " ").strip()
        chunk_count = len(selected)
        return f"{domain} dataset for {task_label} - {chunk_count} samples"

    def _build_dataset_description(self, task_type: str, selected: list[dict]) -> str:
        domain = self._resolve_dataset_domain(selected=selected)
        task_label = task_type.replace("_", " ").strip()
        return f"{task_label.title()} dataset for {domain} built from approved NLP consensus chunks."

    def _create_dataset_chunks(self, dataset: Dataset, selected: list[dict]) -> None:
        # Create mapping rows and mark source NLP chunks as inactive so they aren't reused
        DatasetChunk.objects.bulk_create(
            [DatasetChunk(dataset=dataset, nlp_chunk=item["nlp_chunk"]) for item in selected]
        )
        # Bulk-deactivate selected NLP chunks
        nlp_ids = [item["nlp_chunk"].id for item in selected]
        if nlp_ids:
            NLPChunk.objects.filter(id__in=nlp_ids).update(is_active=False)

    def _create_metrics(self, dataset: Dataset, selected: list[dict]) -> DatasetMetrics:
        total_nlp_chunks = len(selected)
        total_token_count = sum(item["token_count"] for item in selected)
        avg_agreement = sum(item["agreement"] for item in selected) / total_nlp_chunks
        label_counts = Counter(item["label"] for item in selected)
        domain_counts = Counter(item["nlp_chunk"].source_domain or "unknown" for item in selected)
        bytes_size = sum(item["text_bytes"] for item in selected)
        unique_extracted_docs = set()
        expert_review_count = 0

        for item in selected:
            source_chunk = item["nlp_chunk"].source_chunk
            if source_chunk and getattr(source_chunk, "extracted_document_id", None):
                unique_extracted_docs.add(source_chunk.extracted_document_id)

            # Prefer processing-level consensus (Traceable to source QC chunk).
            proc_consensus = getattr(source_chunk, "consensus", None) if source_chunk is not None else None
            if proc_consensus and getattr(proc_consensus, "requires_expert_review", False):
                expert_review_count += 1
                continue

            # Fallback to NLP consensus flag if processing consensus is absent
            nlp_consensus = getattr(item["nlp_chunk"], "consensus", None)
            if nlp_consensus and getattr(nlp_consensus, "requires_expert_review", False):
                expert_review_count += 1

        return DatasetMetrics.objects.create(
            dataset=dataset,
            total_documents=len(unique_extracted_docs),
            chunk_count=total_nlp_chunks,
            token_count=total_token_count,
            avg_qc_score=avg_agreement,
            annotation_coverage=1.0,
            expert_validation_ratio=expert_review_count / total_nlp_chunks if total_nlp_chunks else 0.0,
            dataset_size_bytes=bytes_size,
            computed_at=timezone.now(),
            label_distribution=dict(label_counts),
            domain_distribution=dict(domain_counts),
        )

    def _create_export_asset(self, dataset: Dataset, selected: list[dict], metrics: DatasetMetrics) -> DatasetAsset:
        # Build minimal export content (only text and label) for JSONL, CSV, TSV
        rows = []
        for item in selected:
            nlp_chunk = item["nlp_chunk"]
            text = nlp_chunk.text or ""
            label = item.get("label")
            rows.append({"text": text, "label": label})

        assets = []

        # JSONL
        jsonl_lines = [json.dumps(r, ensure_ascii=False) for r in rows]
        jsonl_content = "\n".join(jsonl_lines) + "\n"
        jsonl_name = f"dataset_{dataset.id}_{dataset.nlp_task_type or 'dataset'}.jsonl"
        asset_jsonl = DatasetAsset(dataset=dataset, file_format=DatasetFileFormatChoices.JSONL, file_size_bytes=len(jsonl_content.encode("utf-8")))
        asset_jsonl.file.save(jsonl_name, ContentFile(jsonl_content.encode("utf-8")), save=False)
        asset_jsonl.save()
        assets.append(asset_jsonl)

        # CSV and TSV
        for fmt, delimiter in ((DatasetFileFormatChoices.CSV, ","), (DatasetFileFormatChoices.TSV, "\t")):
            sio = io.StringIO()
            writer = csv.writer(sio, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
            # header
            writer.writerow(["text", "label"])
            for r in rows:
                writer.writerow([r["text"], r["label"]])
            content = sio.getvalue()
            ext = "csv" if fmt == DatasetFileFormatChoices.CSV else "tsv"
            file_name = f"dataset_{dataset.id}_{dataset.nlp_task_type or 'dataset'}.{ext}"
            asset = DatasetAsset(dataset=dataset, file_format=fmt, file_size_bytes=len(content.encode("utf-8")))
            asset.file.save(file_name, ContentFile(content.encode("utf-8")), save=False)
            asset.save()
            assets.append(asset)

        # Return the JSONL asset as primary
        return assets[0]

    def _serialize_jsonl_row(self, dataset: Dataset, item: dict, metrics: DatasetMetrics) -> str:
        nlp_chunk = item["nlp_chunk"]
        consensus = getattr(nlp_chunk, "consensus", None)
        payload = {
            "dataset_id": str(dataset.id),
            "dataset_title": dataset.title,
            "task_type": dataset.nlp_task_type,
            "nlp_chunk_id": str(nlp_chunk.id),
            "source_chunk_id": str(nlp_chunk.source_chunk_id),
            "text": nlp_chunk.text,
            "label": item["label"],
            "agreement_score": item["agreement"],
            "source_domain": nlp_chunk.source_domain,
            "consensus_resolved_at": getattr(consensus, "resolved_at", None).isoformat() if getattr(consensus, "resolved_at", None) else None,
            "build_config": dataset.build_config,
            "metrics": {
                "chunk_count": metrics.chunk_count,
                "token_count": metrics.token_count,
                "label_distribution": metrics.label_distribution,
                "domain_distribution": metrics.domain_distribution,
            },
        }
        return json.dumps(payload, ensure_ascii=False)
