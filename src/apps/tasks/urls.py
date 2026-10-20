from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.tasks.views import (
    AttachmentViewSet,
    BackgroundTaskDetailView,
    ExternalHolidaysView,
    ProjectViewSet,
    TaskViewSet,
)

app_name = "tasks"

router = DefaultRouter()
router.register(r"projects", ProjectViewSet, basename="project")
router.register(r"tasks", TaskViewSet, basename="task")
router.register(r"attachments", AttachmentViewSet, basename="attachment")


urlpatterns = [
    path("", include(router.urls)),
    path(
        "background-tasks/<str:job_id>/",
        BackgroundTaskDetailView.as_view(),
        name="background-task-detail",
    ),
    path(
        "external/holidays/",
        ExternalHolidaysView.as_view(),
        name="external-holidays",
    ),
]
