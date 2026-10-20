import mimetypes
from typing import Optional

from django.conf import settings
from django.db import connection
from django.db.models import QuerySet
from django.utils import timezone

from apps.tasks.models import Attachment, Project, Task, TaskPriority, TaskStatus, User
from apps.tasks.repositories import (
    AttachmentRepository,
    ProjectRepository,
    TaskRepository,
)


class ServiceError(Exception):
    """Базове виключення для сервісного шару."""

    pass


class EntityNotFoundError(ServiceError):
    """Виключення, що викидається, коли сутність не знайдена."""

    pass


class ValidationError(ServiceError):
    """Виключення, що викидається при помилці валідації бізнес-логіки."""

    pass


class BadRequestError(ServiceError):
    """Виключення, що викидається при некоректному синтаксисі або параметрах запиту."""

    pass


class ProjectService:
    """Сервісний шар для бізнес-логіки проєктів."""

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
        if not owner:
            raise ValidationError("Project owner is required.")
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
    """Сервісний шар для бізнес-логіки завдань."""

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
        assignee: Optional[User | int] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> QuerySet[Task]:
        qs = self.task_repo.get_all()
        if project_id:
            qs = qs.filter(project_id=project_id)
        if assignee:
            if isinstance(assignee, User):
                qs = qs.filter(assignee=assignee)
            else:
                qs = qs.filter(assignee_id=assignee)
        if status:
            qs = qs.filter(status=status)
        if priority:
            qs = qs.filter(priority=priority)
        return qs

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

        if due_date and due_date < timezone.now():
            raise ValidationError("Due date cannot be in the past.")

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

        if "project" in data and isinstance(data["project"], int):
            project = self.project_repo.get_by_id(data["project"])
            if not project:
                raise EntityNotFoundError(
                    f"Project with ID {data['project']} not found."
                )
            data["project"] = project

        if (
            "due_date" in data
            and data["due_date"]
            and data["due_date"] < timezone.now()
        ):
            raise ValidationError("Due date cannot be in the past.")

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
    """Сервісний шар для перевірки працездатності сервісу та БД."""

    @staticmethod
    def check_health() -> dict[str, str]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ok"}


class AttachmentService:
    """Сервісний шар для бізнес-логіки файлів-вкладень."""

    def __init__(
        self,
        attachment_repository: Optional[AttachmentRepository] = None,
        task_repository: Optional[TaskRepository] = None,
    ):
        self.attachment_repo = attachment_repository or AttachmentRepository()
        self.task_repo = task_repository or TaskRepository()

    def validate_file(self, file) -> None:
        if not file:
            raise ValidationError("No file provided.")

        max_size = getattr(settings, "MAX_ATTACHMENT_SIZE_BYTES", 10 * 1024 * 1024)
        if file.size > max_size:
            max_mb = max_size // (1024 * 1024)
            raise ValidationError(
                f"File size exceeds limit of {max_mb} MB (current size: {file.size} bytes)."
            )

        if file.size == 0:
            raise ValidationError("Uploaded file cannot be empty.")

        allowed_exts = getattr(
            settings,
            "ALLOWED_ATTACHMENT_EXTENSIONS",
            ["pdf", "png", "jpg", "jpeg", "docx", "txt"],
        )
        file_name = getattr(file, "name", "")
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext not in allowed_exts:
            raise ValidationError(
                f"File extension '.{ext}' is not allowed. Allowed extensions: {', '.join(allowed_exts)}."
            )

        allowed_mimes = getattr(
            settings,
            "ALLOWED_ATTACHMENT_MIME_TYPES",
            [
                "application/pdf",
                "image/png",
                "image/jpeg",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain",
            ],
        )
        content_type = getattr(file, "content_type", "")
        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(file_name)
            if guessed:
                content_type = guessed

        if content_type not in allowed_mimes:
            raise ValidationError(
                f"MIME type '{content_type}' is not allowed. Allowed types: {', '.join(allowed_mimes)}."
            )

    def list_attachments(self, task_id: Optional[int] = None) -> QuerySet[Attachment]:
        if task_id:
            return self.attachment_repo.get_by_task(task_id)
        return self.attachment_repo.get_all()

    def get_attachment(self, attachment_id: int) -> Attachment:
        attachment = self.attachment_repo.get_by_id(attachment_id)
        if not attachment:
            raise EntityNotFoundError(f"Attachment with ID {attachment_id} not found.")
        return attachment

    def create_attachment(self, task_id: int, file) -> Attachment:
        task = self.task_repo.get_by_id(task_id)
        if not task:
            raise EntityNotFoundError(f"Task with ID {task_id} not found.")

        self.validate_file(file)

        content_type = getattr(file, "content_type", "")
        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(getattr(file, "name", ""))
            content_type = guessed or "application/octet-stream"

        return self.attachment_repo.create(
            task=task,
            file=file,
            file_size=file.size,
            content_type=content_type,
        )

    def delete_attachment(self, attachment_id: int) -> None:
        attachment = self.get_attachment(attachment_id)
        self.attachment_repo.delete(attachment)
