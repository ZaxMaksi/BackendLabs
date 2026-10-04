"""URL configuration for task_tracker project."""

from django.contrib import admin
from django.urls import include, path

from apps.tasks.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    # Службовий ендпоінт health-check (доступний як /health, так і /api/health/)
    path("health/", health_check, name="health-check"),
    path("health", health_check, name="health-check-direct"),
    path("api/health/", health_check, name="api-health-check"),
    path("api/health", health_check, name="api-health-check-direct"),
    path("api/", include("apps.tasks.urls")),
]
