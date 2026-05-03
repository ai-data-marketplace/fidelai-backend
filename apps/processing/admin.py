from django.contrib import admin

from .models import (
	AIQualityCheck,
	Annotation,
	AnnotationTask,
	Chunk,
	Consensus,
	ExpertReview,
	ExpertTask,
	ExpertTaskChunk,
	ExtractedDocument,
	TaskAssignment,
	TaskChunk,
)


@admin.register(ExtractedDocument)
class ExtractedDocumentAdmin(admin.ModelAdmin):
	list_display = ("id", "raw_document", "chunking_status", "processed_at", "created_at")
	list_filter = ("chunking_status", "processed_at", "created_at")
	search_fields = ("id", "raw_document__id", "raw_document__title")
	raw_id_fields = ("raw_document",)
	ordering = ("-processed_at",)


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"extracted_document",
		"status",
		"order_index",
		"char_start",
		"char_end",
		"token_count",
		"created_at",
	)
	list_filter = ("status", "created_at", "updated_at")
	search_fields = ("id", "extracted_document__id", "extracted_document__raw_document__title", "text")
	raw_id_fields = ("extracted_document",)
	ordering = ("extracted_document", "order_index")


@admin.register(AIQualityCheck)
class AIQualityCheckAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"chunk",
		"domain_match",
		"is_amharic",
		"readability",
		"safety_label",
		"confidence",
		"model_name",
		"model_version",
		"processed_at",
	)
	list_filter = (
		"domain_match",
		"is_amharic",
		"readability",
		"safety_label",
		"confidence",
		"processed_at",
	)
	search_fields = ("id", "chunk__id", "model_name", "model_version")
	raw_id_fields = ("chunk",)
	ordering = ("-processed_at",)


@admin.register(AnnotationTask)
class AnnotationTaskAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "domain", "created_by", "total_chunks", "created_at")
	list_filter = ("domain", "created_at")
	search_fields = ("id", "name", "description", "created_by__email", "created_by__username")
	raw_id_fields = ("created_by",)
	ordering = ("-created_at",)


@admin.register(TaskChunk)
class TaskChunkAdmin(admin.ModelAdmin):
	list_display = ("id", "task", "chunk", "order_index", "created_at")
	list_filter = ("created_at",)
	search_fields = ("id", "task__name", "task__id", "chunk__id")
	raw_id_fields = ("task", "chunk")
	ordering = ("task", "order_index")


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(admin.ModelAdmin):
	list_display = ("id", "task", "annotator", "status", "assigned_at", "started_at", "completed_at")
	list_filter = ("status", "assigned_at", "started_at", "completed_at")
	search_fields = ("id", "task__name", "task__id", "annotator__email", "annotator__username")
	raw_id_fields = ("task", "annotator")
	ordering = ("-assigned_at",)


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"chunk",
		"annotator",
		"task_assignment",
		"domain_match",
		"is_amharic",
		"readability",
		"safety_label",
		"confidence",
		"is_skipped",
		"created_at",
	)
	list_filter = (
		"domain_match",
		"is_amharic",
		"readability",
		"safety_label",
		"confidence",
		"is_skipped",
		"created_at",
	)
	search_fields = (
		"id",
		"chunk__id",
		"annotator__email",
		"annotator__username",
		"task_assignment__id",
	)
	raw_id_fields = ("chunk", "annotator", "task_assignment")
	ordering = ("-created_at",)


@admin.register(Consensus)
class ConsensusAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"chunk",
		"final_domain_match",
		"agreement_score",
		"requires_expert_review",
		"total_annotations",
		"computed_at",
	)
	list_filter = ("final_domain_match", "requires_expert_review", "computed_at")
	search_fields = ("id", "chunk__id")
	raw_id_fields = ("chunk",)
	ordering = ("-computed_at",)


@admin.register(ExpertTask)
class ExpertTaskAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "domain", "created_at")
	list_filter = ("domain", "created_at")
	search_fields = ("id", "name")
	ordering = ("-created_at",)


@admin.register(ExpertTaskChunk)
class ExpertTaskChunkAdmin(admin.ModelAdmin):
	list_display = ("id", "expert_task", "chunk", "created_at")
	list_filter = ("created_at",)
	search_fields = ("id", "expert_task__name", "expert_task__id", "chunk__id")
	raw_id_fields = ("expert_task", "chunk")


@admin.register(ExpertReview)
class ExpertReviewAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"chunk",
		"expert",
		"domain_match",
		"is_amharic",
		"readability",
		"safety_label",
		"confidence",
		"created_at",
	)
	list_filter = (
		"domain_match",
		"is_amharic",
		"readability",
		"safety_label",
		"confidence",
		"created_at",
	)
	search_fields = ("id", "chunk__id", "expert__email", "expert__username")
	raw_id_fields = ("chunk", "expert")
	ordering = ("-created_at",)
