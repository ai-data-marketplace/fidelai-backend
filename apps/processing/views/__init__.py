from .annotation_views import (
    AcceptTaskAssignmentView,
    DeclineTaskAssignmentView,
    MyAssignmentsListView,
    SubmitChunkAnnotationView,
    TaskAssignmentChunksView,
    TaskAssignmentProgressView,
)

from .expert_review_views import (
    ExpertTaskListAPIView,
    ExpertTaskAcceptAPIView,
    ExpertTaskDeclineAPIView,
    ExpertTaskChunksAPIView,
    ExpertTaskProgressAPIView,
    ExpertChunkResolveAPIView,
)

__all__ = [
    "AcceptTaskAssignmentView",
    "DeclineTaskAssignmentView",
    "MyAssignmentsListView",
    "SubmitChunkAnnotationView",
    "TaskAssignmentChunksView",
    "TaskAssignmentProgressView",
    "ExpertTaskListAPIView",
    "ExpertTaskAcceptAPIView",
    "ExpertTaskDeclineAPIView",
    "ExpertTaskChunksAPIView",
    "ExpertTaskProgressAPIView",
    "ExpertChunkResolveAPIView",
]
