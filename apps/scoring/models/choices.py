from django.db import models


class ScoreActionTypeChoices(models.TextChoices):
    # Contributor events
    DOCUMENT_APPROVED = "document_approved", "Document Approved"
    DATASET_INCLUDED = "dataset_included", "Dataset Included"
    DATASET_SOLD = "dataset_sold", "Dataset Sold"

    # Annotator events
    ANNOTATION_SUBMITTED = "annotation_submitted", "Annotation Submitted"
    ANNOTATION_MATCH_CONSENSUS = "annotation_match_consensus", "Annotation Match Consensus"
    ANNOTATION_BELOW_THRESHOLD = "annotation_below_threshold", "Annotation Below Threshold"

    # Expert events
    EXPERT_REVIEW_COMPLETED = "expert_review_completed", "Expert Review Completed"
    CONFLICT_RESOLVED = "conflict_resolved", "Conflict Resolved"