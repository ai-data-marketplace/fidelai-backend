"""DRF serializers for the NLP annotation workflow API."""

from __future__ import annotations

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.nlp.models.choices import NLPTaskTypeChoices, SentimentLabelChoices


class NLPPreviousAnnotationSerializer(serializers.Serializer):
    annotation_id = serializers.UUIDField(source="id", read_only=True)
    labels = serializers.JSONField(read_only=True)
    confidence_score = serializers.DecimalField(max_digits=5, decimal_places=4, read_only=True, allow_null=True)
    time_spent_seconds = serializers.IntegerField(read_only=True, allow_null=True)
    notes = serializers.CharField(read_only=True, allow_blank=True)
    created_at = serializers.DateTimeField(read_only=True)


class NLPTaskListSerializer(serializers.Serializer):
    task_id = serializers.UUIDField(source="task.id", read_only=True)
    name = serializers.CharField(source="task.name", read_only=True)
    domain = serializers.CharField(source="task.domain", read_only=True, allow_blank=True)
    task_type = serializers.CharField(source="task.task_type", read_only=True)
    status = serializers.CharField(read_only=True)
    total_chunks = serializers.IntegerField(source="task.total_chunks", read_only=True)


class NLPTaskChunkSerializer(serializers.Serializer):
    chunk_id = serializers.UUIDField(source="nlp_chunk.id", read_only=True)
    order_index = serializers.IntegerField(read_only=True)
    text = serializers.CharField(source="nlp_chunk.text", read_only=True)
    previous_annotation = serializers.SerializerMethodField()

    def get_previous_annotation(self, obj):
        annotations = getattr(obj.nlp_chunk, "user_annotations", []) or []
        if not annotations:
            return None
        return NLPPreviousAnnotationSerializer(annotations[0]).data


class NLPTaskDetailSerializer(serializers.Serializer):
    task_id = serializers.UUIDField(source="task.id", read_only=True)
    name = serializers.CharField(source="task.name", read_only=True)
    domain = serializers.CharField(source="task.domain", read_only=True, allow_blank=True)
    task_type = serializers.CharField(source="task.task_type", read_only=True)
    status = serializers.CharField(read_only=True)
    total_chunks = serializers.IntegerField(source="task.total_chunks", read_only=True)
    chunks = NLPTaskChunkSerializer(source="task.task_chunks", many=True, read_only=True)


class NLPTaskAssignmentActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class NLPAnnotationCreateSerializer(serializers.Serializer):
    labels = serializers.JSONField()
    confidence_score = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1)
    time_spent_seconds = serializers.IntegerField(min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_labels(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("labels must be a JSON object.")
        if not value:
            raise serializers.ValidationError("labels cannot be empty.")
        # If view/service provided a chunk in context, enforce task-specific rules
        chunk = self.context.get("chunk")
        if chunk is not None:
            task_type = getattr(chunk, "task_type", None)
            self._validate_task_specific_labels(task_type, value)

        return value

    def _validate_task_specific_labels(self, task_type: str | None, labels: dict):
        """Enforce task-specific label structure for known NLP tasks.

        Currently implements strict checks for `sentiment` task_type. Other
        task types can be added here as needed.
        """
        if task_type is None:
            return

        if task_type == NLPTaskTypeChoices.SENTIMENT:
            # Expect single key 'sentiment' with one of the allowed values
            if "sentiment" not in labels:
                raise ValidationError({"details": "Missing required key 'sentiment' for sentiment tasks."})
            val = labels.get("sentiment")
            allowed = {c.value for c in SentimentLabelChoices}
            if not isinstance(val, str) or val not in allowed:
                raise ValidationError({
                    "details": f"Invalid sentiment value. Expected one of: {sorted(allowed)}."
                })
        # future task_type validations (NER, topic_classification, etc.) go here


class NLPTaskProgressSerializer(serializers.Serializer):
    task_id = serializers.UUIDField(read_only=True)
    total_chunks = serializers.IntegerField(read_only=True)
    annotated_chunks = serializers.IntegerField(read_only=True)
    remaining_chunks = serializers.IntegerField(read_only=True)
    completion_percentage = serializers.IntegerField(read_only=True)
