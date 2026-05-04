from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ScoreConfigViewSet, MyScoreView

router = DefaultRouter()
router.register(r"score-configs", ScoreConfigViewSet, basename="scoreconfig")

urlpatterns = [
	path("", include(router.urls)),
	path("my-score/", MyScoreView.as_view(), name="my-score"),
]
