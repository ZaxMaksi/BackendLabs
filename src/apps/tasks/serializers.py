from rest_framework import serializers

from apps.tasks.models import Project, Task, User


class UserSerializer(serializers.ModelSerializer):
    """Сериализатор для модели User."""

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "first_name", "last_name"]
        read_only_fields = ["id"]


class ProjectSerializer(serializers.ModelSerializer):
    """Сериализатор для модели Project."""

    owner = UserSerializer(read_only=True)

    class Meta:
        model = Project
        fields = ["id", "name", "description", "created_at", "owner"]
        read_only_fields = ["id", "created_at", "owner"]


class TaskSerializer(serializers.ModelSerializer):
    """Сериализатор для модели Task."""

    assignee = UserSerializer(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "project",
            "assignee",
            "due_date",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
