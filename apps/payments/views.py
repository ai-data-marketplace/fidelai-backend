from __future__ import annotations

from decimal import Decimal

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from apps.marketplace.services.dataset_purchase_service import DatasetPurchaseService
from apps.payments.serializers.withdrawal_serializers import (
    WalletDetailsSerializer,
    WithdrawalRequestCreateSerializer,
    WithdrawalRequestSerializer,
)
from apps.payments.services.chapa_client import ChapaClient, ChapaClientError
from apps.payments.services.withdrawal_service import WithdrawalService


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


class WalletDetailsView(APIView):
    """Get wallet and withdrawable amount details for authenticated user."""

    permission_classes = [IsAuthenticated]
    @extend_schema(
		responses={200: WalletDetailsSerializer}
	)
    def get(self, request):
        try:
            details = WithdrawalService.calculate_withdrawable_amount(
                request.user)
            serializer = WalletDetailsSerializer(details)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ChapaBankListView(APIView):
    """Expose Chapa supported banks so the frontend can render names and codes."""

    permission_classes = [AllowAny]

    def get(self, request):
        try:
            provider_response = ChapaClient().list_banks()
        except ChapaClientError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        banks = provider_response.get("data")
        if banks is None:
            banks = provider_response

        return Response(
            {
                "detail": "Banks retrieved successfully.",
                "banks": banks,
                "provider_response": provider_response,
            },
            status=status.HTTP_200_OK,
        )


class WithdrawalRequestInitiateView(APIView):
    """Initiate a withdrawal request with on-demand score-to-money conversion."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=WithdrawalRequestCreateSerializer,
    )
    def post(self, request):
        serializer = WithdrawalRequestCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            result = WithdrawalService().initiate_withdrawal_request(
                user=request.user,
                bank_code=serializer.validated_data["bank_code"],
                account_number=serializer.validated_data["account_number"],
                account_name=serializer.validated_data["account_name"],
                amount=serializer.validated_data["amount"],
            )
        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        withdrawal_request = result["withdrawal_request"]
        response_serializer = WithdrawalRequestSerializer(withdrawal_request)
        response_data = {
            **response_serializer.data,
            "transfer_reference": result["transfer_reference"],
            "transfer_response": result["transfer_response"],
            "verification_response": result["verification_response"],
        }
        return Response(response_data, status=status.HTTP_201_CREATED)


class WithdrawalTransferVerifyView(APIView):
    """Verify a Chapa transfer and finalize the withdrawal when successful."""

    permission_classes = [AllowAny]

    def get(self, request):
        return self._handle_verify(request)

    def post(self, request):
        return self._handle_verify(request)

    def _handle_verify(self, request):
        tx_ref = (
            request.query_params.get("tx_ref")
            or request.query_params.get("reference")
            or request.data.get("tx_ref")
            or request.data.get("reference")
        )
        try:
            result = WithdrawalService.verify_and_finalize_transfer(tx_ref=tx_ref)
        except Exception as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "detail": "Withdrawal transfer verified successfully.",
                "transfer_reference": result["transfer_reference"],
                "withdrawal_request_id": str(result["withdrawal_request"].id),
                "provider_response": result["provider_response"],
            },
            status=status.HTTP_200_OK,
        )
