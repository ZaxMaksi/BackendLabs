"""URL configuration for task_tracker project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.tasks.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI v3 Schema and Interactive Documentation (Swagger UI & Redoc)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    # Health-check endpoints
    path("health/", health_check, name="health-check"),
    path("health", health_check, name="health-check-direct"),
    path("api/health/", health_check, name="api-health-check"),
    path("api/health", health_check, name="api-health-check-direct"),
    # API endpoints
    path("api/", include("apps.tasks.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
