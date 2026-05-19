from django.urls import path
from apps.marketplace.views import (
	DatasetDetailView,
	DatasetListView,
	DatasetPurchaseInitiateView,
	DatasetPurchaseVerifyView,
	InventoryListView,
	DownloadAssetView,
)

urlpatterns = [
	path("datasets/", DatasetListView.as_view(), name="marketplace-dataset-list"),
	path("datasets/<uuid:pk>/", DatasetDetailView.as_view(), name="marketplace-dataset-detail"),
	path("datasets/<uuid:pk>/purchase/", DatasetPurchaseInitiateView.as_view(), name="marketplace-dataset-purchase"),
	path("purchases/verify/", DatasetPurchaseVerifyView.as_view(), name="marketplace-purchase-verify"),
	path("purchases/", InventoryListView.as_view(), name="marketplace-purchases"),
	path(
		"purchases/<uuid:purchase_id>/assets/<uuid:asset_pk>/download/",
		DownloadAssetView.as_view(),
		name="marketplace-purchase-asset-download",
	),
]
