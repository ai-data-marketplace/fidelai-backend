from django.urls import path
from apps.marketplace.views import DatasetDetailView, DatasetListView, DatasetPurchaseInitiateView

urlpatterns = [
	path("datasets/", DatasetListView.as_view(), name="marketplace-dataset-list"),
	path("datasets/<uuid:pk>/", DatasetDetailView.as_view(), name="marketplace-dataset-detail"),
	path("datasets/<uuid:pk>/purchase/", DatasetPurchaseInitiateView.as_view(), name="marketplace-dataset-purchase"),
]
