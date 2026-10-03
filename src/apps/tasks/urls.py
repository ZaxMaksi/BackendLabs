from django.urls import path

from apps.tasks.views import health_check

app_name = "tasks"

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("health", health_check, name="health-check-noslash"),
]
