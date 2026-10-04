from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.tasks.views import ProjectViewSet, TaskViewSet, health_check

app_name = "tasks"

router = DefaultRouter()
router.register(r"projects", ProjectViewSet, basename="project")
router.register(r"tasks", TaskViewSet, basename="task")

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("health", health_check, name="health-check-noslash"),
    path("", include(router.urls)),
]
