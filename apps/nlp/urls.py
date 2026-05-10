from django.urls import path

from apps.nlp.views import (
    NLPChunkAnnotationCreateView,
    NLPTaskAcceptView,
    NLPTaskDeclineView,
    NLPTaskDetailView,
    NLPTaskListView,
    NLPTaskProgressView,
)

urlpatterns = [
    path("tasks/", NLPTaskListView.as_view(), name="nlp-task-list"),
    path("tasks/<uuid:task_id>/", NLPTaskDetailView.as_view(), name="nlp-task-detail"),
    path("tasks/<uuid:task_id>/accept/", NLPTaskAcceptView.as_view(), name="nlp-task-accept"),
    path("tasks/<uuid:task_id>/decline/", NLPTaskDeclineView.as_view(), name="nlp-task-decline"),
    path("tasks/<uuid:task_id>/progress/", NLPTaskProgressView.as_view(), name="nlp-task-progress"),
    path("chunks/<uuid:chunk_id>/annotate/", NLPChunkAnnotationCreateView.as_view(), name="nlp-chunk-annotate"),
]
