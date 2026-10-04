from django.utils import timezone
from rest_framework import serializers

from apps.tasks.models import Project, Task, TaskPriority, TaskStatus, User


class UserSerializer(serializers.ModelSerializer):
    """Сериализатор для модели User."""

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "first_name", "last_name"]
        read_only_fields = ["id"]


class ProjectShortSerializer(serializers.ModelSerializer):
    """Краткое представление проекта для вложенного отображения."""

    class Meta:
        model = Project
        fields = ["id", "name", "description"]
        read_only_fields = ["id", "name", "description"]


class TaskInProjectSerializer(serializers.ModelSerializer):
    """Вложенное представление задачи внутри проекта."""

    assignee = UserSerializer(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "assignee",
            "due_date",
            "created_at",
        ]
        read_only_fields = fields


class ProjectSerializer(serializers.ModelSerializer):
    """Сериализатор для модели Project с поддержкой CRUD и связей One-to-Many."""

    owner = UserSerializer(read_only=True)
    owner_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="owner",
        write_only=True,
        required=False,
    )
    tasks = TaskInProjectSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "description",
            "created_at",
            "owner",
            "owner_id",
            "tasks",
        ]
        read_only_fields = ["id", "created_at", "owner", "tasks"]

    def to_internal_value(self, data):
        # Поддержка передачи идентификатора владельца как через owner_id, так и через owner
        if isinstance(data, dict):
            data = data.copy()
            if (
                "owner" in data
                and not isinstance(data["owner"], dict)
                and "owner_id" not in data
            ):
                data["owner_id"] = data.pop("owner")
        return super().to_internal_value(data)

    def validate_name(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("Project name cannot be empty or blank.")
        return value.strip()

    def validate(self, attrs):
        request = self.context.get("request")
        if self.instance is None and "owner" not in attrs:
            if request and hasattr(request, "user") and request.user.is_authenticated:
                attrs["owner"] = request.user
            else:
                first_user = User.objects.first()
                if first_user:
                    attrs["owner"] = first_user
                else:
                    raise serializers.ValidationError(
                        {"owner": "Owner is required for project creation."}
                    )
        return attrs


class TaskSerializer(serializers.ModelSerializer):
    """Сериализатор для модели Task с валидацией полей, дат и связей."""

    project = ProjectShortSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        source="project",
        write_only=True,
        required=True,
    )
    assignee = UserSerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="assignee",
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "project",
            "project_id",
            "assignee",
            "assignee_id",
            "due_date",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "project", "assignee"]

    def to_internal_value(self, data):
        # Поддержка передачи id проекта и исполнителя как 'project' / 'assignee'
        if isinstance(data, dict):
            data = data.copy()
            if (
                "project" in data
                and not isinstance(data["project"], dict)
                and "project_id" not in data
            ):
                data["project_id"] = data.pop("project")
            if (
                "assignee" in data
                and not isinstance(data["assignee"], dict)
                and "assignee_id" not in data
            ):
                data["assignee_id"] = data.pop("assignee")
        return super().to_internal_value(data)

    def validate_title(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("Task title cannot be empty or blank.")
        return value.strip()

    def validate_status(self, value: str) -> str:
        if value not in TaskStatus.values:
            raise serializers.ValidationError(
                f"Invalid status '{value}'. Allowed values: {TaskStatus.values}"
            )
        return value

    def validate_priority(self, value: str) -> str:
        if value not in TaskPriority.values:
            raise serializers.ValidationError(
                f"Invalid priority '{value}'. Allowed values: {TaskPriority.values}"
            )
        return value

    def validate_due_date(self, value):
        if value and value < timezone.now():
            raise serializers.ValidationError("Due date cannot be in the past.")
        return value
