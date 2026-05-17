from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.marketplace.services.dataset_purchase_service import DatasetPurchaseService


class ChapaCallbackView(APIView):
	permission_classes = [AllowAny]

	def get(self, request):
		return self._handle_callback(request)

	def post(self, request):
		return self._handle_callback(request)

	def _handle_callback(self, request):
		tx_ref = (
			request.query_params.get("tx_ref")
			or request.query_params.get("trx_ref")
			or request.query_params.get("reference")
			or request.data.get("tx_ref")
			or request.data.get("trx_ref")
			or request.data.get("reference")
		)
		service = DatasetPurchaseService()
		result = service.verify_and_finalize(tx_ref=tx_ref)
		return Response(
			{
				"detail": "Payment verified successfully.",
				"order_number": result["order"].order_number,
				"dataset_id": str(result["order_item"].dataset_id),
				"purchase_id": str(result["purchase"].id),
				"tx_ref": tx_ref,
				"provider_response": result["provider_response"],
			},
			status=status.HTTP_200_OK,
		)
