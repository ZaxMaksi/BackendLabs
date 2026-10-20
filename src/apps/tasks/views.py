import os

from django.http import FileResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tasks.external import ExternalCalendarService
from apps.tasks.filters import ProjectFilter, TaskFilter
from apps.tasks.pagination import StandardResultsSetPagination
from apps.tasks.serializers import (
    AttachmentSerializer,
    BackgroundTaskAcceptedSerializer,
    BackgroundTaskStatusSerializer,
    ExternalHolidaysResponseSerializer,
    ProjectSerializer,
    TaskSerializer,
)
from apps.tasks.services import (
    AttachmentService,
    BadRequestError,
    HealthCheckService,
    ProjectReportService,
    ProjectService,
    TaskService,
)


@extend_schema(
    summary="Health check service",
    description="Службовий ендпоінт health-check для перевірки працездатності веб-сервісу та підключення до бази даних PostgreSQL.",
    tags=["Health"],
    responses={
        200: OpenApiResponse(
            response=dict,
            description="Сервіс та база даних повністю функціональні.",
            examples=[
                OpenApiExample(
                    name="Success Health Check",
                    value={"status": "ok"},
                    status_codes=["200"],
                )
            ],
        ),
        503: OpenApiResponse(
            response=dict,
            description="Сервіс або база даних недоступні.",
            examples=[
                OpenApiExample(
                    name="Service Unavailable",
                    value={
                        "status": "error",
                        "detail": "connection to server at 'localhost' failed",
                    },
                    status_codes=["503"],
                )
            ],
        ),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Службовий ендпоінт health-check для моніторингу працездатності сервісу та БД."""
    try:
        data = HealthCheckService.check_health()
        return Response(data, status=status.HTTP_200_OK)
    except Exception as exc:
        return Response(
            {"status": "error", "detail": str(exc)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@extend_schema_view(
    list=extend_schema(
        summary="List all projects",
        description="Отримати пагінований список проєктів з підтримкою фільтрації (?owner_id=), пошуку та сортування (?ordering=created_at).",
        tags=["Projects"],
    ),
    retrieve=extend_schema(
        summary="Retrieve project details",
        description="Отримати детальну інформацію про проєкт за ID, включаючи власника та пов'язані завдання.",
        tags=["Projects"],
    ),
    create=extend_schema(
        summary="Create new project",
        description="Створити новий проєкт. Потрібно вказати назву (name), опис (description) та ID власника (owner_id).",
        tags=["Projects"],
        examples=[
            OpenApiExample(
                name="Project Creation Example",
                value={
                    "name": "E-Commerce System",
                    "description": "Backend API development for online shop",
                    "owner": 1,
                },
                request_only=True,
            )
        ],
    ),
    update=extend_schema(
        summary="Update project",
        description="Повне оновлення даних проєкту за вказаним ID.",
        tags=["Projects"],
    ),
    partial_update=extend_schema(
        summary="Partially update project",
        description="Часткове оновлення полів проєкту за вказаним ID.",
        tags=["Projects"],
    ),
    destroy=extend_schema(
        summary="Delete project",
        description="Видалити проєкт та всі пов'язані з ним завдання.",
        tags=["Projects"],
    ),
)
class ProjectViewSet(viewsets.ModelViewSet):
    """ViewSet для повного CRUD-управління проєктами."""

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
        self.project_report_service = ProjectReportService()

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

    @extend_schema(
        summary="Generate project report in background",
        description=(
            "Запустити асинхронну генерацію підсумкового аналітичного звіту за проєктом "
            "у фоновому потоці без блокування клієнта (відповідь HTTP 202 Accepted)."
        ),
        tags=["Projects", "Background Tasks"],
        responses={
            202: OpenApiResponse(
                response=BackgroundTaskAcceptedSerializer,
                description="Завдання успішно прийнято до фонового виконання.",
            ),
            404: OpenApiResponse(description="Проєкт не знайдено (RFC 7807)"),
        },
    )
    @action(detail=True, methods=["post"], url_path="generate-report")
    def generate_report(self, request, pk=None):
        project = self.get_object()
        job_id = self.project_report_service.start_project_report_generation(
            project.id
        )
        check_url = request.build_absolute_uri(f"/api/background-tasks/{job_id}/")
        return Response(
            {
                "status": "accepted",
                "message": (
                    f"Project summary report generation started for project '{project.name}'."
                ),
                "job_id": job_id,
                "check_status_url": check_url,
            },
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema_view(
    list=extend_schema(
        summary="List all tasks",
        description="Отримати список завдань з підтримкою фільтрації (?status=, ?priority=, ?project_id=, ?assignee_id=), пагінації та сортування.",
        tags=["Tasks"],
    ),
    retrieve=extend_schema(
        summary="Retrieve task details",
        description="Отримати інформацію про завдання за ID, включаючи проєкт та виконавця.",
        tags=["Tasks"],
    ),
    create=extend_schema(
        summary="Create new task",
        description="Створити нове завдання в системі. Обов'язкові поля: title, project_id.",
        tags=["Tasks"],
        examples=[
            OpenApiExample(
                name="Task Creation Example",
                value={
                    "title": "Design REST API Endpoints",
                    "description": "Implement Stage 3 OpenAPI & attachments",
                    "project": 1,
                    "status": "todo",
                    "priority": "high",
                    "due_date": "2026-12-31T23:59:59Z",
                },
                request_only=True,
            )
        ],
    ),
    update=extend_schema(
        summary="Update task",
        description="Повне оновлення даних завдання за його ID.",
        tags=["Tasks"],
    ),
    partial_update=extend_schema(
        summary="Partially update task",
        description="Часткове оновлення полів завдання (наприклад, статусу або виконавця).",
        tags=["Tasks"],
    ),
    destroy=extend_schema(
        summary="Delete task",
        description="Видалити завдання за його ID.",
        tags=["Tasks"],
    ),
)
class TaskViewSet(viewsets.ModelViewSet):
    """ViewSet для повного CRUD-управління завданнями."""

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
        self.attachment_service = AttachmentService()

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

    @extend_schema(
        methods=["GET"],
        summary="List attachments for task",
        description="Отримати список усіх вкладень, прикріплених до цього завдання.",
        tags=["Tasks", "Attachments"],
        responses={200: AttachmentSerializer(many=True)},
    )
    @extend_schema(
        methods=["POST"],
        summary="Upload attachment for task",
        description="Завантажити новий файл-вкладення безпосередньо до поточного завдання.",
        tags=["Tasks", "Attachments"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                },
                "required": ["file"],
            }
        },
        responses={201: AttachmentSerializer},
    )
    @action(
        detail=True,
        methods=["get", "post"],
        url_path="attachments",
        parser_classes=[MultiPartParser, FormParser],
    )
    def attachments(self, request, pk=None):
        task = self.get_object()
        if request.method == "GET":
            qs = self.attachment_service.list_attachments(task_id=task.id)
            serializer = AttachmentSerializer(
                qs, many=True, context={"request": request}
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response(
                {
                    "type": "urn:problem-type:unprocessable-entity",
                    "title": "Unprocessable Entity",
                    "status": 422,
                    "detail": "File is required.",
                    "instance": request.path,
                    "invalid_params": {"file": ["No file provided."]},
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        attachment = self.attachment_service.create_attachment(
            task_id=task.id, file=file_obj
        )
        serializer = AttachmentSerializer(attachment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(
        summary="List all attachments",
        description="Отримати список вкладень із можливістю фільтрації за завданням (?task_id=...).",
        parameters=[
            OpenApiParameter(
                name="task_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Фільтрувати вкладення за ID завдання",
            )
        ],
        tags=["Attachments"],
    ),
    retrieve=extend_schema(
        summary="Retrieve attachment details",
        description="Отримати детальну інформацію про конкретне вкладення (ID, завдання, URL, розмір, MIME-тип).",
        tags=["Attachments"],
    ),
    create=extend_schema(
        summary="Upload new attachment",
        description="Завантажити новий файл-вкладення через multipart/form-data. Валідується розмір (до 10 МБ) та розширення/MIME-тип.",
        tags=["Attachments"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                    "task_id": {"type": "integer"},
                },
                "required": ["file", "task_id"],
            }
        },
        responses={201: AttachmentSerializer},
    ),
    destroy=extend_schema(
        summary="Delete attachment",
        description="Видалити вкладення та фізичний файл зі сховища.",
        tags=["Attachments"],
    ),
)
class AttachmentViewSet(viewsets.ModelViewSet):
    """ViewSet для завантаження, перегляду та видалення файлів-вкладень."""

    serializer_class = AttachmentSerializer
    pagination_class = StandardResultsSetPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.attachment_service = AttachmentService()

    def get_queryset(self):
        task_id = self.request.query_params.get("task_id")
        if task_id:
            try:
                task_id_int = int(task_id)
                return self.attachment_service.list_attachments(task_id=task_id_int)
            except ValueError:
                return self.attachment_service.list_attachments().none()
        return self.attachment_service.list_attachments()

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        pk = self.kwargs[lookup_url_kwarg]
        try:
            pk_int = int(pk)
        except (ValueError, TypeError):
            raise NotFound(f"Invalid attachment ID: '{pk}'.")
        instance = self.attachment_service.get_attachment(pk_int)
        self.check_object_permissions(self.request, instance)
        return instance

    def perform_create(self, serializer):
        task = serializer.validated_data.get("task")
        if not task:
            raise serializers.ValidationError({"task_id": "Task is required."})
        uploaded_file = serializer.validated_data.get("file")
        if not uploaded_file:
            raise serializers.ValidationError({"file": "File is required."})

        instance = self.attachment_service.create_attachment(
            task_id=task.id,
            file=uploaded_file,
        )
        serializer.instance = instance

    def perform_destroy(self, instance):
        self.attachment_service.delete_attachment(instance.id)

    @extend_schema(
        summary="Download attachment file",
        description="Завантажити (скачати) файл вкладення з відповідними заголовками Content-Disposition та Content-Type.",
        tags=["Attachments"],
        responses={(200, "*/*"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        instance = self.get_object()
        try:
            file_obj = instance.file.open("rb")
        except Exception:
            raise NotFound("File not found on storage.")

        filename = os.path.basename(instance.file.name)
        response = FileResponse(
            file_obj,
            content_type=instance.content_type or "application/octet-stream",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = str(instance.file_size)
        return response


class BackgroundTaskDetailView(APIView):
    """Ендпоінт моніторингу стану виконання фонового завдання."""

    permission_classes = [AllowAny]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.project_report_service = ProjectReportService()

    @extend_schema(
        summary="Get background task status",
        description=(
            "Отримати поточний стан фонового завдання за його job_id "
            "(pending, running, completed, failed) та агрегований результат виконання."
        ),
        tags=["Background Tasks"],
        parameters=[
            OpenApiParameter(
                name="job_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="Унікальний UUID фонового завдання",
            )
        ],
        responses={
            200: OpenApiResponse(
                response=BackgroundTaskStatusSerializer,
                description="Інформація про стан виконання фонового завдання.",
            ),
            404: OpenApiResponse(description="Фонове завдання не знайдено (RFC 7807)."),
        },
    )
    def get(self, request, job_id: str):
        task_status = self.project_report_service.get_task_status(job_id)
        serializer = BackgroundTaskStatusSerializer(task_status)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ExternalHolidaysView(APIView):
    """Ендпоінт інтеграції із зовнішнім REST API виробничого календаря та свят."""

    permission_classes = [AllowAny]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calendar_service = ExternalCalendarService()

    @extend_schema(
        summary="Get public holidays for year and country",
        description=(
            "Отримати перелік державних свят та неробочих днів для планування дедлайнів завдань. "
            "Виконує стійкий запит до зовнішнього REST API з таймаутом та обов'язковим "
            "кешуванням у пам'яті (LocMemCache)."
        ),
        tags=["External Services"],
        parameters=[
            OpenApiParameter(
                name="year",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Рік (за замовчуванням поточний рік)",
                required=False,
            ),
            OpenApiParameter(
                name="country_code",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Дволітерний код країни ISO 3166-1 alpha-2 (за замовчуванням UA)",
                required=False,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ExternalHolidaysResponseSerializer,
                description="Список святкових днів успішно отримано.",
            ),
            400: OpenApiResponse(description="Некоректні параметри запиту (RFC 7807)."),
            503: OpenApiResponse(description="Зовнішній сервіс недоступний (RFC 7807)."),
            504: OpenApiResponse(
                description="Перевищено таймаут очікування зовнішнього сервісу (RFC 7807)."
            ),
        },
    )
    def get(self, request):
        year_raw = request.query_params.get("year")
        country_code = request.query_params.get("country_code", "UA").strip().upper()

        if year_raw:
            try:
                year = int(year_raw)
                if year < 1900 or year > 2100:
                    raise ValueError()
            except ValueError:
                raise BadRequestError(
                    "Parameter 'year' must be an integer between 1900 and 2100."
                )
        else:
            from django.utils import timezone

            year = timezone.now().year

        if not country_code or len(country_code) != 2:
            raise BadRequestError(
                "Parameter 'country_code' must be a 2-letter ISO country code (e.g. UA, US)."
            )

        data = self.calendar_service.get_public_holidays(
            year=year, country_code=country_code
        )
        serializer = ExternalHolidaysResponseSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
