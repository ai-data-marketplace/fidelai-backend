from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.processing.models import (
    Annotation,
    Chunk,
    ConfidenceChoices,
    DomainMatchChoices,
    ReadabilityChoices,
    SafetyChoices,
    TaskAssignment,
    TaskAssignmentStatusChoices,
    TaskChunk,
)


class TaskAssignmentListSerializer(serializers.Serializer):
    assignment_id = serializers.UUIDField(source="id", read_only=True)
    task_id = serializers.UUIDField(source="task.id", read_only=True)
    task_name = serializers.CharField(source="task.name", read_only=True)
    domain = serializers.CharField(source="task.domain", read_only=True)
    description = serializers.CharField(source="task.description", read_only=True)
    status = serializers.CharField(read_only=True)
    assigned_at = serializers.DateTimeField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    total_chunks = serializers.IntegerField(read_only=True)
    annotated_chunks = serializers.IntegerField(read_only=True)
    progress_percentage = serializers.SerializerMethodField()

    def get_progress_percentage(self, obj):
        total_chunks = getattr(obj, "total_chunks", 0) or 0
        annotated_chunks = getattr(obj, "annotated_chunks", 0) or 0
        return int((annotated_chunks / total_chunks) * 100) if total_chunks else 0


class AnnotationDetailSerializer(serializers.Serializer):
    """Serializes annotation data for prepopulating form fields on resume/back navigation."""
    annotation_id = serializers.UUIDField(source="id", read_only=True)
    domain_match = serializers.CharField(read_only=True)
    is_amharic = serializers.BooleanField(read_only=True)
    readability = serializers.CharField(read_only=True)
    safety_label = serializers.CharField(read_only=True)
    confidence = serializers.CharField(read_only=True)
    notes = serializers.CharField(read_only=True, allow_blank=True)
    time_spent_seconds = serializers.IntegerField(read_only=True, allow_null=True)
    is_skipped = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class TaskChunkSerializer(serializers.Serializer):
    chunk_id = serializers.UUIDField(source="chunk.id", read_only=True)
    order_index = serializers.IntegerField(read_only=True)
    text = serializers.CharField(source="chunk.text", read_only=True)
    token_count = serializers.IntegerField(source="chunk.token_count", read_only=True)
    domain = serializers.CharField(source="task.domain", read_only=True)
    metadata = serializers.JSONField(source="chunk.metadata", read_only=True)
    annotation_exists = serializers.BooleanField(read_only=True)
    annotation = serializers.SerializerMethodField()

    def get_annotation(self, obj):
        """Return full annotation data if exists, null otherwise."""
        annotation = obj.chunk.annotations.first() if obj.chunk.annotations.exists() else None
        if annotation:
            return AnnotationDetailSerializer(annotation).data
        return None


class AnnotationCreateSerializer(serializers.Serializer):
    task_assignment = serializers.PrimaryKeyRelatedField(queryset=TaskAssignment.objects.select_related("task", "annotator"))
    domain_match = serializers.ChoiceField(choices=DomainMatchChoices.choices)
    is_amharic = serializers.BooleanField()
    readability = serializers.ChoiceField(choices=ReadabilityChoices.choices)
    safety_label = serializers.ChoiceField(choices=SafetyChoices.choices)
    confidence = serializers.ChoiceField(choices=ConfidenceChoices.choices)
    notes = serializers.CharField(required=False, allow_blank=True)
    time_spent_seconds = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    is_skipped = serializers.BooleanField(default=False)

    def validate(self, attrs):
        request = self.context.get("request")
        chunk = self.context.get("chunk")
        assignment = attrs["task_assignment"]

        if not request or not request.user.is_authenticated:
            raise PermissionDenied("You do not have permission to access this assignment.")

        if assignment.annotator_id != request.user.id:
            raise PermissionDenied("You do not have permission to access this assignment.")

        if assignment.status not in (
            TaskAssignmentStatusChoices.ACCEPTED,
            TaskAssignmentStatusChoices.IN_PROGRESS,
        ):
            raise ValidationError({"detail": "Task must be accepted before annotation."})

        if chunk is None:
            raise ValidationError({"detail": "Chunk does not belong to this assignment."})

        if not TaskChunk.objects.filter(task=assignment.task, chunk=chunk).exists():
            raise ValidationError({"detail": "Chunk does not belong to this assignment."})

        return attrs


class TaskProgressSerializer(serializers.Serializer):
    assignment_id = serializers.UUIDField(read_only=True)
    total_chunks = serializers.IntegerField(read_only=True)
    completed_annotations = serializers.IntegerField(read_only=True)
    skipped_annotations = serializers.IntegerField(read_only=True)
    remaining_chunks = serializers.IntegerField(read_only=True)
    progress_percentage = serializers.IntegerField(read_only=True)
    assignment_status = serializers.CharField(read_only=True)


class AnnotationSubmitResponseSerializer(serializers.Serializer):
    message = serializers.CharField(read_only=True)
    annotation_id = serializers.UUIDField(read_only=True)
    assignment_status = serializers.CharField(read_only=True)
    progress = TaskProgressSerializer(read_only=True)
