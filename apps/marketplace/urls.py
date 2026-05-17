from django.urls import path
from apps.marketplace.views import DatasetListView, DatasetDetailView

urlpatterns = [
	path("datasets/", DatasetListView.as_view(), name="marketplace-dataset-list"),
	path("datasets/<uuid:pk>/", DatasetDetailView.as_view(), name="marketplace-dataset-detail"),
]
