"""
Django admin configuration for NLP app.

Provides admin interface for managing NLP annotation tasks and results.
"""

from django.contrib import admin

from apps.nlp.models import (
    NLPChunk,
    NLPAnnotationTask,
    NLPTaskChunk,
    NLPTaskAssignment,
    NLPAnnotation,
    NLPConsensus,
)


@admin.register(NLPChunk)
class NLPChunkAdmin(admin.ModelAdmin):
    """Admin for NLP chunks."""
    
    list_display = [
        "id",
        "source_chunk_id",
        "task_type",
        "status",
        "is_active",
        "generated_by_ai",
        "created_at",
    ]
    list_filter = [
        "task_type",
        "status",
        "is_active",
        "generated_by_ai",
        "created_at",
    ]
    search_fields = ["text", "source_domain", "id"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fieldsets = (
        ("Identification", {
            "fields": ("id", "source_chunk")
        }),
        ("Task Configuration", {
            "fields": ("task_type", "status")
        }),
        ("Content", {
            "fields": ("text", "order_index", "char_start", "char_end")
        }),
        ("AI Extraction", {
            "fields": (
                "generated_by_ai",
                "ai_model_name",
                "ai_confidence_score",
                "requires_human_review",
            ),
            "classes": ("collapse",)
        }),
        ("Context", {
            "fields": ("source_context", "source_domain"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("metadata",),
            "classes": ("collapse",)
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )


@admin.register(NLPAnnotationTask)
class NLPAnnotationTaskAdmin(admin.ModelAdmin):
    """Admin for NLP annotation tasks."""
    
    list_display = [
        "id",
        "task_type",
        "name",
        "domain",
        "total_chunks",
        "is_active",
        "created_at",
    ]
    list_filter = ["task_type", "domain", "is_active", "created_at"]
    search_fields = ["name", "description", "id"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fieldsets = (
        ("Identification", {
            "fields": ("id", "name")
        }),
        ("Task Configuration", {
            "fields": ("task_type", "domain")
        }),
        ("Details", {
            "fields": ("description", "total_chunks")
        }),
        ("Management", {
            "fields": ("created_by", "is_active")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )


@admin.register(NLPTaskChunk)
class NLPTaskChunkAdmin(admin.ModelAdmin):
    """Admin for NLP task chunks."""
    
    list_display = ["id", "task_id", "nlp_chunk_id", "order_index"]
    list_filter = ["task"]
    search_fields = ["task_id", "nlp_chunk_id"]
    fieldsets = (
        ("Assignment", {
            "fields": ("task", "nlp_chunk", "order_index")
        }),
    )


@admin.register(NLPTaskAssignment)
class NLPTaskAssignmentAdmin(admin.ModelAdmin):
    """Admin for NLP task assignments."""
    
    list_display = [
        "id",
        "task_id",
        "annotator",
        "status",
        "assigned_at",
        "completed_at",
    ]
    list_filter = ["status", "assigned_at", "task__task_type"]
    search_fields = ["annotator__username", "task__name", "id"]
    readonly_fields = ["id", "assigned_at", "created_at", "updated_at"]
    fieldsets = (
        ("Identification", {
            "fields": ("id",)
        }),
        ("Assignment", {
            "fields": ("task", "annotator")
        }),
        ("Status", {
            "fields": ("status",)
        }),
        ("Timeline", {
            "fields": ("assigned_at", "started_at", "completed_at")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )


@admin.register(NLPAnnotation)
class NLPAnnotationAdmin(admin.ModelAdmin):
    """Admin for NLP annotations."""
    
    list_display = [
        "id",
        "nlp_chunk_id",
        "annotator",
        "task_type",
        "is_skipped",
        "created_at",
    ]
    list_filter = ["task_type", "is_skipped", "created_at"]
    search_fields = ["nlp_chunk_id", "annotator__username", "id"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fieldsets = (
        ("Identification", {
            "fields": ("id",)
        }),
        ("References", {
            "fields": ("nlp_chunk", "annotator", "task_assignment")
        }),
        ("Task", {
            "fields": ("task_type",)
        }),
        ("Labels", {
            "fields": ("labels", "is_skipped")
        }),
        ("Notes & Metrics", {
            "fields": (
                "notes",
                "confidence_score",
                "time_spent_seconds",
            )
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )


@admin.register(NLPConsensus)
class NLPConsensusAdmin(admin.ModelAdmin):
    """Admin for NLP consensus results."""
    
    list_display = [
        "id",
        "nlp_chunk_id",
        "task_type",
        "agreement_score",
        "total_annotations",
        "requires_expert_review",
        "computed_at",
    ]
    list_filter = [
        "task_type",
        "requires_expert_review",
        "computed_at",
    ]
    search_fields = ["nlp_chunk_id", "id"]
    readonly_fields = ["id", "computed_at", "created_at", "updated_at"]
    fieldsets = (
        ("Identification", {
            "fields": ("id", "nlp_chunk")
        }),
        ("Task", {
            "fields": ("task_type",)
        }),
        ("Consensus Result", {
            "fields": ("final_labels",)
        }),
        ("Metrics", {
            "fields": ("agreement_score", "total_annotations")
        }),
        ("Workflow", {
            "fields": ("requires_expert_review",)
        }),
        ("Timestamps", {
            "fields": ("computed_at", "created_at", "updated_at")
        }),
    )
