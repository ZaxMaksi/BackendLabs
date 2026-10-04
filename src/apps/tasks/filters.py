import django_filters

from apps.tasks.models import Project, Task, TaskPriority, TaskStatus


class TaskFilter(django_filters.FilterSet):
    """Фильтр для задач по статусу, приоритету, проекту и исполнителю."""

    status = django_filters.ChoiceFilter(choices=TaskStatus.choices)
    priority = django_filters.ChoiceFilter(choices=TaskPriority.choices)
    project_id = django_filters.NumberFilter(field_name="project_id")
    project = django_filters.NumberFilter(field_name="project_id")
    assignee_id = django_filters.NumberFilter(field_name="assignee_id")
    assignee = django_filters.NumberFilter(field_name="assignee_id")

    class Meta:
        model = Task
        fields = [
            "status",
            "priority",
            "project_id",
            "project",
            "assignee_id",
            "assignee",
        ]


class ProjectFilter(django_filters.FilterSet):
    """Фильтр для проектов по владельцу и названию."""

    owner_id = django_filters.NumberFilter(field_name="owner_id")
    owner = django_filters.NumberFilter(field_name="owner_id")
    name = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = Project
        fields = ["owner_id", "owner", "name"]
