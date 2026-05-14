
from rest_framework import serializers

from apps.processing.models import (
    Consensus,
    Chunk,
)
from apps.processing.models.chunk import (
    DomainMatchChoices,
    ReadabilityChoices,
    SafetyChoices,
    ConfidenceChoices,
    ChunkStatusChoices,
)


class ExpertTaskListSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="expert_task.id", read_only=True)
    name = serializers.CharField(source="expert_task.name", read_only=True)
    domain = serializers.CharField(source="expert_task.domain", read_only=True)
    status = serializers.CharField(read_only=True)
    assigned_at = serializers.DateTimeField(read_only=True)
    total_chunks = serializers.IntegerField(source="expert_task.total_chunks", read_only=True)


class ConsensusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consensus
        fields = (
            "final_domain_match",
            "final_is_amharic",
            "final_readability",
            "final_safety_label",
            "agreement_score",
            "requires_expert_review",
            "total_annotations",
            "computed_at",
        )


class SourceInfoSerializer(serializers.Serializer):
    raw_document_id = serializers.IntegerField(source="extracted_document.raw_document.id", read_only=True)
    title = serializers.CharField(source="extracted_document.raw_document.title", read_only=True)


class ExpertChunkTaskSerializer(serializers.Serializer):
    chunk_id = serializers.UUIDField(source="chunk.id", read_only=True)
    text = serializers.CharField(source="chunk.text", read_only=True)
    domain = serializers.CharField(read_only=True)
    metadata = serializers.JSONField(source="chunk.metadata", read_only=True)
    quality_score = serializers.FloatField(source="chunk.quality_score", read_only=True)
    consensus = ConsensusSerializer(source="chunk.consensus", read_only=True)
    source = SourceInfoSerializer(source="chunk", read_only=True)
    annotation_count = serializers.IntegerField(read_only=True)


class ExpertTaskProgressSerializer(serializers.Serializer):
    assignment_id = serializers.UUIDField(read_only=True)
    total_chunks = serializers.IntegerField(read_only=True)
    reviewed_chunks = serializers.IntegerField(read_only=True)
    remaining_chunks = serializers.IntegerField(read_only=True)
    progress_percentage = serializers.IntegerField(read_only=True)
    assignment_status = serializers.CharField(read_only=True)


class ExpertReviewSubmissionSerializer(serializers.Serializer):
    domain_match = serializers.ChoiceField(choices=DomainMatchChoices.choices)
    is_amharic = serializers.BooleanField()
    readability = serializers.ChoiceField(choices=ReadabilityChoices.choices)
    safety_label = serializers.ChoiceField(choices=SafetyChoices.choices)
    confidence = serializers.ChoiceField(choices=ConfidenceChoices.choices)
    notes = serializers.CharField(allow_blank=True, required=False)
    resolution_reasoning = serializers.CharField()
    final_decision = serializers.ChoiceField(choices=[(ChunkStatusChoices.APPROVED, ChunkStatusChoices.APPROVED), (ChunkStatusChoices.REJECTED, ChunkStatusChoices.REJECTED), (ChunkStatusChoices.RESOLVED, ChunkStatusChoices.RESOLVED)])

    def validate_final_decision(self, value):
        if value not in (ChunkStatusChoices.APPROVED, ChunkStatusChoices.REJECTED, ChunkStatusChoices.RESOLVED):
            raise serializers.ValidationError("Invalid final_decision")
        return value
