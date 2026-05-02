from django.urls import path

from apps.processing.views import (
	AcceptTaskAssignmentView,
	DeclineTaskAssignmentView,
	MyAssignmentsListView,
	SubmitChunkAnnotationView,
	TaskAssignmentChunksView,
	TaskAssignmentProgressView,
)

urlpatterns = [
	path("my-assignments/", MyAssignmentsListView.as_view(), name="my-assignments"),
	path("assignments/<uuid:id>/accept/", AcceptTaskAssignmentView.as_view(), name="accept-assignment"),
	path("assignments/<uuid:id>/decline/", DeclineTaskAssignmentView.as_view(), name="decline-assignment"),
	path("assignments/<uuid:id>/chunks/", TaskAssignmentChunksView.as_view(), name="assignment-chunks"),
	path("chunks/<uuid:chunk_id>/annotate/", SubmitChunkAnnotationView.as_view(), name="chunk-annotate"),
	path("assignments/<uuid:id>/progress/", TaskAssignmentProgressView.as_view(), name="assignment-progress"),
]
