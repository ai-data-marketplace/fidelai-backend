"""
Service to enrich dataset detail responses with sample chunks and contributor information.
"""

from typing import Optional
from django.db.models import Prefetch, Count, Q

from apps.datasets.models.dataset import Dataset
from apps.datasets.models.chunk_map import DatasetChunk
from apps.nlp.models.nlp_chunk import NLPChunk


class DatasetDetailService:
    """Enriches dataset detail with samples and metadata."""

    def enrich_dataset_detail(self, dataset: Dataset, sample_limit: int = 10) -> dict:
        """
        Enriches a dataset with sample chunks and contributor metadata.

        Args:
            dataset: The Dataset instance to enrich
            sample_limit: Number of sample chunks to include (default 10)

        Returns:
            Dict with keys:
            - samples: list of dicts with text, label, quality_score
            - sample_quality_scores: list of quality scores for visualization
            - total_contributors: count of unique contributors
        """
        # Fetch dataset chunks with related NLPChunk, linked consensus, and source traceability
        dataset_chunks = (
            DatasetChunk.objects
            .filter(dataset=dataset)
            .select_related(
                "nlp_chunk",
                "nlp_chunk__consensus",
                "nlp_chunk__source_chunk",
                "nlp_chunk__source_chunk__extracted_document",
                "nlp_chunk__source_chunk__extracted_document__raw_document",
                "nlp_chunk__source_chunk__extracted_document__raw_document__user",
            )
            .order_by("id")  # Ordered selection
        )

        # Collect samples and contributor tracking
        samples = []
        contributor_ids = set()
        
        for i, dataset_chunk in enumerate(dataset_chunks):
            if i >= sample_limit:
                break
            
            nlp_chunk = dataset_chunk.nlp_chunk
            consensus = getattr(nlp_chunk, "consensus", None)
            
            # Extract label from consensus final_labels
            label = self._extract_label(consensus)
            
            # Extract quality score from ai_confidence_score (use as-is, it's final score)
            quality_score = float(nlp_chunk.ai_confidence_score) if nlp_chunk.ai_confidence_score else 0.0
            
            # Track contributor
            try:
                user = nlp_chunk.source_chunk.extracted_document.raw_document.user
                if user and user.id:
                    contributor_ids.add(user.id)
            except (AttributeError, TypeError):
                pass
            
            samples.append({
                "text": nlp_chunk.text or "",
                "label": label or "unknown",
                "quality_score": round(quality_score, 4),
            })
        
        quality_scores = [s["quality_score"] for s in samples]
        
        return {
            "samples": samples,
            "sample_quality_scores": quality_scores,
            "total_contributors": len(contributor_ids),
        }

    def _extract_label(self, consensus) -> Optional[str]:
        """Extract label from consensus final_labels."""
        if not consensus:
            return None
        
        final_labels = getattr(consensus, "final_labels", None)
        if not isinstance(final_labels, dict):
            return None
        
        # Try to return a string value
        for value in final_labels.values():
            if isinstance(value, (str, int, float)):
                return str(value)
        
        return None
