from __future__ import annotations

from django.db.models import Q, Prefetch
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination

from apps.datasets.models.dataset import Dataset
from apps.datasets.models.assets import DatasetAsset
from apps.datasets.models.metrics import DatasetMetrics
from apps.marketplace.serializers import DatasetListSerializer, DatasetDetailSerializer


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
