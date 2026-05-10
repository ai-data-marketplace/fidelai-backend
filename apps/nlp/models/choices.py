"""
NLP app choice models for task types, statuses, and labels.
These extend the QC annotation pipeline for NLP-specific tasks.
"""

from django.db import models


class NLPTaskTypeChoices(models.TextChoices):
    """
    Available NLP task types.
    Extensible for future NLP tasks.
    """
    SENTIMENT = "sentiment", "Sentiment Analysis"
    NER = "ner", "Named Entity Recognition"
    TOPIC_CLASSIFICATION = "topic_classification", "Topic Classification"
    INTENT_DETECTION = "intent_detection", "Intent Detection"
    TOXICITY_CLASSIFICATION = "toxicity_classification", "Toxicity Classification"


class NLPChunkStatusChoices(models.TextChoices):
    """
    Lifecycle statuses for NLP chunks.
    Tracks progression from extraction through approval.
    """
    PENDING_EXTRACTION = "pending_extraction", "Pending Extraction"
    READY_FOR_ANNOTATION = "ready_for_annotation", "Ready for Annotation"
    IN_ANNOTATION = "in_annotation", "In Annotation"
    CONSENSUS_READY = "consensus_ready", "Consensus Ready"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class NLPTaskAssignmentStatusChoices(models.TextChoices):
    """
    Assignment workflow statuses for annotators.
    """
    ASSIGNED = "assigned", "Assigned"
    ACCEPTED = "accepted", "Accepted"
    IN_PROGRESS = "in_progress", "In Progress"
    SUBMITTED = "submitted", "Submitted"
    DECLINED = "declined", "Declined"


class SentimentLabelChoices(models.TextChoices):
    """
    Labels for sentiment analysis tasks.
    Used when task_type is SENTIMENT.
    """
    POSITIVE = "positive", "Positive"
    NEGATIVE = "negative", "Negative"
    NEUTRAL = "neutral", "Neutral"
