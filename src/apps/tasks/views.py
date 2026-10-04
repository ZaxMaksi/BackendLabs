from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.tasks.filters import ProjectFilter, TaskFilter
from apps.tasks.pagination import StandardResultsSetPagination
from apps.tasks.serializers import ProjectSerializer, TaskSerializer
from apps.tasks.services import HealthCheckService, ProjectService, TaskService


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Служебный эндпоинт health-check для мониторинга работоспособности сервиса и БД."""
    try:
        data = HealthCheckService.check_health()
        return Response(data, status=status.HTTP_200_OK)
    except Exception as exc:
        return Response(
            {"status": "error", "detail": str(exc)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class ProjectViewSet(viewsets.ModelViewSet):
    """ViewSet для полного CRUD-управления проектами."""

    serializer_class = ProjectSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    filterset_class = ProjectFilter
    ordering_fields = ["created_at", "name", "id"]
    ordering = ["-created_at"]
    search_fields = ["name", "description"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.project_service = ProjectService()

    def get_queryset(self):
        return self.project_service.list_projects()

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        pk = self.kwargs[lookup_url_kwarg]
        try:
            pk_int = int(pk)
        except (ValueError, TypeError):
            raise NotFound(f"Invalid project ID: '{pk}'.")
        instance = self.project_service.get_project(pk_int)
        self.check_object_permissions(self.request, instance)
        return instance

    def perform_create(self, serializer):
        owner = serializer.validated_data.get("owner")
        if not owner and self.request.user.is_authenticated:
            owner = self.request.user
        instance = self.project_service.create_project(
            name=serializer.validated_data["name"],
            owner=owner,
            description=serializer.validated_data.get("description"),
        )
        serializer.instance = instance

    def perform_update(self, serializer):
        data = dict(serializer.validated_data)
        instance = self.project_service.update_project(
            project_id=serializer.instance.id,
            **data,
        )
        serializer.instance = instance

    def perform_destroy(self, instance):
        self.project_service.delete_project(instance.id)


class TaskViewSet(viewsets.ModelViewSet):
    """ViewSet для полного CRUD-управления задачами."""

    serializer_class = TaskSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    filterset_class = TaskFilter
    ordering_fields = ["created_at", "due_date", "priority", "title", "id"]
    ordering = ["-created_at"]
    search_fields = ["title", "description"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.task_service = TaskService()

    def get_queryset(self):
        return self.task_service.list_tasks()

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        pk = self.kwargs[lookup_url_kwarg]
        try:
            pk_int = int(pk)
        except (ValueError, TypeError):
            raise NotFound(f"Invalid task ID: '{pk}'.")
        instance = self.task_service.get_task(pk_int)
        self.check_object_permissions(self.request, instance)
        return instance

    def perform_create(self, serializer):
        data = dict(serializer.validated_data)
        project = data.pop("project")
        project_id = project.id if hasattr(project, "id") else project
        instance = self.task_service.create_task(
            project_id=project_id,
            **data,
        )
        serializer.instance = instance

    def perform_update(self, serializer):
        data = dict(serializer.validated_data)
        if "project" in data:
            project = data.pop("project")
            data["project_id"] = project.id if hasattr(project, "id") else project
        instance = self.task_service.update_task(
            task_id=serializer.instance.id,
            **data,
        )
        serializer.instance = instance

    def perform_destroy(self, instance):
        self.task_service.delete_task(instance.id)
