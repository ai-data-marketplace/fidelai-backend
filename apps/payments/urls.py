from django.urls import path
from apps.payments.views import ChapaCallbackView

urlpatterns = [
	path("chapa/callback/", ChapaCallbackView.as_view(), name="payments-chapa-callback"),
]
