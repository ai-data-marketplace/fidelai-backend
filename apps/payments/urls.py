from django.urls import path
from apps.payments.views import (
    ChapaBankListView,
    ChapaCallbackView,
    WalletDetailsView,
	WithdrawalTransferVerifyView,
    WithdrawalRequestInitiateView,
    WithdrawalRequestListView,
)

urlpatterns = [
	path("chapa/callback/", ChapaCallbackView.as_view(), name="payments-chapa-callback"),
	path("banks/", ChapaBankListView.as_view(), name="payments-banks-list"),
	path("wallet-details/", WalletDetailsView.as_view(), name="payments-wallet-details"),
	path("withdrawals/", WithdrawalRequestInitiateView.as_view(), name="payments-withdrawal-initiate"),
	path("withdrawals/list/", WithdrawalRequestListView.as_view(), name="payments-withdrawal-list"),
	path("withdrawals/verify/", WithdrawalTransferVerifyView.as_view(), name="payments-withdrawal-transfer-verify"),
]
