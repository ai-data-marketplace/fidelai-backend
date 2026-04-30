from django.urls import path, include
from django.contrib import admin
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),

    # OpenAPI schema & docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/documents/', include('apps.documents.urls')),
    # path('api/v1/processing/', include('apps.processing.urls')),
    # path('api/v1/datasets/', include('apps.datasets.urls')),
    # path('api/v1/marketplace/', include('apps.marketplace.urls')),
    # path('api/v1/scoring/', include('apps.scoring.urls')),
    # path('api/v1/payments/', include('apps.payments.urls')),
    # path('api/v1/notifications/', include('apps.notifications.urls')),
]
