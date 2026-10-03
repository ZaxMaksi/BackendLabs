from typing import Optional

from django.db import connection
from django.db.models import QuerySet

from apps.tasks.models import Project, Task, TaskPriority, TaskStatus, User
from apps.tasks.repositories import ProjectRepository, TaskRepository


class ServiceError(Exception):
    """Базовое исключение для сервисного слоя."""

    pass


class EntityNotFoundError(ServiceError):
    """Исключение, выбрасываемое когда сущность не найдена."""

    pass


class ValidationError(ServiceError):
    """Исключение, выбрасываемое при ошибке валидации бизнес-логики."""

    pass


class ProjectService:
    """Сервисный слой для бизнес-логики проектов."""

    def __init__(self, repository: Optional[ProjectRepository] = None):
        self.repository = repository or ProjectRepository()

    def list_projects(self) -> QuerySet[Project]:
        return self.repository.get_all()

    def get_project(self, project_id: int) -> Project:
        project = self.repository.get_by_id(project_id)
        if not project:
            raise EntityNotFoundError(f"Project with ID {project_id} not found.")
        return project

    def list_user_projects(self, owner: User) -> QuerySet[Project]:
        return self.repository.get_by_owner(owner)

    def create_project(
        self, name: str, owner: User, description: Optional[str] = None
    ) -> Project:
        clean_name = name.strip() if name else ""
        if not clean_name:
            raise ValidationError("Project name cannot be empty.")
        return self.repository.create(
            name=clean_name, owner=owner, description=description
        )

    def update_project(self, project_id: int, **data) -> Project:
        project = self.get_project(project_id)
        if "name" in data:
            clean_name = data["name"].strip() if data["name"] else ""
            if not clean_name:
                raise ValidationError("Project name cannot be empty.")
            data["name"] = clean_name
        return self.repository.update(project, **data)

    def delete_project(self, project_id: int) -> None:
        project = self.get_project(project_id)
        self.repository.delete(project)


class TaskService:
    """Сервисный слой для бизнес-логики задач."""

    def __init__(
        self,
        task_repository: Optional[TaskRepository] = None,
        project_repository: Optional[ProjectRepository] = None,
    ):
        self.task_repo = task_repository or TaskRepository()
        self.project_repo = project_repository or ProjectRepository()

    def list_tasks(
        self,
        project_id: Optional[int] = None,
        assignee: Optional[User] = None,
    ) -> QuerySet[Task]:
        if project_id:
            return self.task_repo.get_by_project(project_id)
        if assignee:
            return self.task_repo.get_by_assignee(assignee)
        return self.task_repo.get_all()

    def get_task(self, task_id: int) -> Task:
        task = self.task_repo.get_by_id(task_id)
        if not task:
            raise EntityNotFoundError(f"Task with ID {task_id} not found.")
        return task

    def create_task(
        self,
        title: str,
        project_id: int,
        description: Optional[str] = None,
        status: str = TaskStatus.TODO,
        priority: str = TaskPriority.MEDIUM,
        assignee: Optional[User] = None,
        due_date=None,
    ) -> Task:
        clean_title = title.strip() if title else ""
        if not clean_title:
            raise ValidationError("Task title cannot be empty.")

        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise EntityNotFoundError(f"Project with ID {project_id} not found.")

        if status not in TaskStatus.values:
            raise ValidationError(
                f"Invalid status '{status}'. Allowed values: {TaskStatus.values}"
            )

        if priority not in TaskPriority.values:
            raise ValidationError(
                f"Invalid priority '{priority}'. Allowed values: {TaskPriority.values}"
            )

        return self.task_repo.create(
            title=clean_title,
            project=project,
            description=description,
            status=status,
            priority=priority,
            assignee=assignee,
            due_date=due_date,
        )

    def update_task(self, task_id: int, **data) -> Task:
        task = self.get_task(task_id)

        if "title" in data:
            clean_title = data["title"].strip() if data["title"] else ""
            if not clean_title:
                raise ValidationError("Task title cannot be empty.")
            data["title"] = clean_title

        if "status" in data and data["status"] not in TaskStatus.values:
            raise ValidationError(
                f"Invalid status '{data['status']}'. Allowed values: {TaskStatus.values}"
            )

        if "priority" in data and data["priority"] not in TaskPriority.values:
            raise ValidationError(
                f"Invalid priority '{data['priority']}'. Allowed values: {TaskPriority.values}"
            )

        if "project_id" in data:
            project = self.project_repo.get_by_id(data["project_id"])
            if not project:
                raise EntityNotFoundError(
                    f"Project with ID {data['project_id']} not found."
                )
            data["project"] = project
            del data["project_id"]

        return self.task_repo.update(task, **data)

    def delete_task(self, task_id: int) -> None:
        task = self.get_task(task_id)
        self.task_repo.delete(task)

    def change_task_status(self, task_id: int, new_status: str) -> Task:
        if new_status not in TaskStatus.values:
            raise ValidationError(
                f"Invalid status '{new_status}'. Allowed values: {TaskStatus.values}"
            )
        return self.update_task(task_id, status=new_status)

    def assign_task(self, task_id: int, assignee: Optional[User]) -> Task:
        return self.update_task(task_id, assignee=assignee)


class HealthCheckService:
    """Сервисный слой для проверки работоспособности сервиса и БД."""

    @staticmethod
    def check_health() -> dict[str, str]:
        # Проверяем доступность подключения к БД
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ok"}
