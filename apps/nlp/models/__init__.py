"""
NLP app models.

Models for the secondary NLP annotation pipeline.
Separate from QC annotation, processing, and marketplace.
"""

from apps.nlp.models.choices import (
    NLPTaskTypeChoices,
    NLPChunkStatusChoices,
    NLPTaskAssignmentStatusChoices,
    SentimentLabelChoices,
)
from apps.nlp.models.nlp_chunk import NLPChunk
from apps.nlp.models.nlp_task import NLPAnnotationTask, NLPTaskChunk
from apps.nlp.models.nlp_annotation import NLPTaskAssignment, NLPAnnotation
from apps.nlp.models.nlp_consensus import NLPConsensus

__all__ = [
    # Choices
    "NLPTaskTypeChoices",
    "NLPChunkStatusChoices",
    "NLPTaskAssignmentStatusChoices",
    "SentimentLabelChoices",
    # Models
    "NLPChunk",
    "NLPAnnotationTask",
    "NLPTaskChunk",
    "NLPTaskAssignment",
    "NLPAnnotation",
    "NLPConsensus",
]
