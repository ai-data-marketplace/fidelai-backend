from django.urls import path, include
from django.contrib import admin
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),

    # OpenAPI schema & docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/auth/', include('apps.users.urls')),
    path('api/scoring/', include('apps.scoring.urls')),
    path('api/documents/', include('apps.documents.urls')),
    path('api/processing/', include('apps.processing.urls')),
    path('api/nlp/', include('apps.nlp.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    # path('api/v1/datasets/', include('apps.datasets.urls')),
    path('api/marketplace/', include('apps.marketplace.urls')),
    # path('api/v1/payments/', include('apps.payments.urls')),
]


from django.conf import settings
from django.conf.urls.static import static
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)