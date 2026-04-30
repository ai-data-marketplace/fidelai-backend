from django.urls import path

from apps.documents.views import (
    DocumentSubmitView,
    MySubmissionDetailView,
    MySubmissionsView,
)

urlpatterns = [
    path("submit/", DocumentSubmitView.as_view(), name="document-submit"),
    path("my-submissions/", MySubmissionsView.as_view(), name="document-my-submissions"),
    path("my-submissions/<uuid:pk>/", MySubmissionDetailView.as_view(), name="document-my-submission-detail"),
]
