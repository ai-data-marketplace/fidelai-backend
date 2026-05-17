from __future__ import annotations

from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from apps.datasets.models.dataset import Dataset
from apps.datasets.models.assets import DatasetAsset
from apps.datasets.models.metrics import DatasetMetrics
from apps.marketplace.serializers import (
	DatasetDetailSerializer,
	DatasetListSerializer,
	DatasetPurchaseInitSerializer,
	InventoryPurchaseSerializer,
)
from apps.marketplace.services.dataset_purchase_service import DatasetPurchaseService
from apps.marketplace.models.purchase import DatasetPurchase
from apps.datasets.models.assets import DatasetAsset


class MarketplacePagination(PageNumberPagination):
	page_size = 4
	page_size_query_param = "page_size"
	max_page_size = 100


class DatasetListView(generics.ListAPIView):
	permission_classes = [AllowAny]
	serializer_class = DatasetListSerializer
	pagination_class = MarketplacePagination

	def get_queryset(self):
		qs = (
			Dataset.objects.select_related("metrics", "created_by", "approved_by")
			.prefetch_related(Prefetch("assets", queryset=DatasetAsset.objects.all()))
			.order_by("-created_at")
		)

		# filters
		q = self.request.query_params.get("q")
		if q:
			qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(build_config__icontains=q))

		domain = self.request.query_params.get("domain")
		if domain:
			qs = qs.filter(domain__iexact=domain)

		year = self.request.query_params.get("year")
		if year and year.isdigit():
			qs = qs.filter(collection_year=int(year))

		min_size = self.request.query_params.get("min_size")
		max_size = self.request.query_params.get("max_size")
		if min_size or max_size:
			qs = qs.filter(metrics__chunk_count__isnull=False)
			if min_size and min_size.isdigit():
				qs = qs.filter(metrics__chunk_count__gte=int(min_size))
			if max_size and max_size.isdigit():
				qs = qs.filter(metrics__chunk_count__lte=int(max_size))

		min_price = self.request.query_params.get("min_price")
		max_price = self.request.query_params.get("max_price")
		if min_price:
			try:
				qs = qs.filter(price__gte=float(min_price))
			except ValueError:
				pass
		if max_price:
			try:
				qs = qs.filter(price__lte=float(max_price))
			except ValueError:
				pass

		ordering = self.request.query_params.get("ordering")
		if ordering == "oldest":
			qs = qs.order_by("created_at")
		else:
			qs = qs.order_by("-created_at")

		return qs


class DatasetDetailView(generics.RetrieveAPIView):
	permission_classes = [AllowAny]
	serializer_class = DatasetDetailSerializer
	queryset = Dataset.objects.select_related("metrics", "created_by", "approved_by").prefetch_related(
		Prefetch("assets", queryset=DatasetAsset.objects.all())
	)


class DatasetPurchaseInitiateView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request, pk):
		dataset = get_object_or_404(
			Dataset.objects.select_related("metrics", "created_by", "approved_by").prefetch_related(
				Prefetch("assets", queryset=DatasetAsset.objects.all())
			),
			pk=pk,
		)
		service = DatasetPurchaseService()
		result = service.initialize_purchase(buyer=request.user, dataset=dataset, request=request)
		payload = {
			"order_number": result["order"].order_number,
			"tx_ref": result["tx_ref"],
			"checkout_url": result["checkout_url"],
			"amount": result["order"].total_amount,
			"currency": result["order"].currency,
			"dataset_id": dataset.id,
			"dataset_title": dataset.title,
		}
		return Response(DatasetPurchaseInitSerializer(payload).data, status=status.HTTP_201_CREATED)


class InventoryListView(generics.ListAPIView):
	permission_classes = [IsAuthenticated]
	serializer_class = InventoryPurchaseSerializer
	pagination_class = MarketplacePagination

	def get_queryset(self):
		user = getattr(self.request, "user", None)
		if not user or user.is_anonymous:
			return DatasetPurchase.objects.none()

		qs = (
			DatasetPurchase.objects.filter(buyer=user)
			.select_related("order_item__order", "dataset")
			.prefetch_related(Prefetch("dataset__assets", queryset=DatasetAsset.objects.all()))
			.order_by("-purchased_at")
		)

		return qs


class DownloadAssetView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request, purchase_id, asset_pk):
		# verify purchase belongs to user
		purchase = get_object_or_404(DatasetPurchase, pk=purchase_id, buyer=request.user)

		# fetch asset and ensure it belongs to the purchased dataset
		asset = get_object_or_404(DatasetAsset, pk=asset_pk)
		if getattr(asset, "dataset_id", None) != getattr(purchase, "dataset_id", None):
			raise Http404("Asset not found for this purchase.")

		# increment metrics on the purchase
		purchase.download_count = (purchase.download_count or 0) + 1
		purchase.last_downloaded_at = timezone.now()
		purchase.save(update_fields=["download_count", "last_downloaded_at"])

		# serve the file using storage backend
		file_field = getattr(asset, "file", None)
		if not file_field:
			raise Http404("No file available for this asset.")

		fh = file_field.open("rb")
		filename = file_field.name.split("/")[-1] if getattr(file_field, "name", None) else None
		return FileResponse(fh, as_attachment=True, filename=filename)
