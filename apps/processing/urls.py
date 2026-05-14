from django.urls import path

from apps.processing.views.annotation_views import (
	AcceptTaskAssignmentView,
	DeclineTaskAssignmentView,
	MyAssignmentsListView,
	SubmitChunkAnnotationView,
	TaskAssignmentChunksView,
	TaskAssignmentProgressView,
)
from apps.processing.views.expert_review_views import (
    ExpertTaskListAPIView,
    ExpertTaskAcceptAPIView,
    ExpertTaskDeclineAPIView,
	ExpertTaskChunksAPIView,
    ExpertChunkResolveAPIView,
)

urlpatterns = [
	path("my-assignments/", MyAssignmentsListView.as_view(), name="my-assignments"),
	path("assignments/<uuid:id>/accept/", AcceptTaskAssignmentView.as_view(), name="accept-assignment"),
	path("assignments/<uuid:id>/decline/", DeclineTaskAssignmentView.as_view(), name="decline-assignment"),
	path("assignments/<uuid:id>/chunks/", TaskAssignmentChunksView.as_view(), name="assignment-chunks"),
	path("chunks/<uuid:chunk_id>/annotate/", SubmitChunkAnnotationView.as_view(), name="chunk-annotate"),
	path("assignments/<uuid:id>/progress/", TaskAssignmentProgressView.as_view(), name="assignment-progress"),
	# Expert review endpoints
	path("expert/tasks/", ExpertTaskListAPIView.as_view(), name="expert-tasks-list"),
	path("expert/tasks/<uuid:id>/accept/", ExpertTaskAcceptAPIView.as_view(), name="expert-task-accept"),
	path("expert/tasks/<uuid:id>/decline/", ExpertTaskDeclineAPIView.as_view(), name="expert-task-decline"),
	path("expert/tasks/<uuid:id>/chunks/", ExpertTaskChunksAPIView.as_view(), name="expert-task-chunks"),
	path("expert/chunks/<uuid:chunk_id>/resolve/", ExpertChunkResolveAPIView.as_view(), name="expert-chunk-resolve"),
]
