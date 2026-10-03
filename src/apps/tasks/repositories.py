from typing import Optional

from django.db.models import QuerySet

from apps.tasks.models import Project, Task, TaskPriority, TaskStatus, User, UserRole


class UserRepository:
    """Репозиторий для изоляции ORM-запросов к сущности User."""

    def get_all(self) -> QuerySet[User]:
        return User.objects.all()

    def get_by_id(self, user_id: int) -> Optional[User]:
        return User.objects.filter(id=user_id).first()

    def get_by_username(self, username: str) -> Optional[User]:
        return User.objects.filter(username=username).first()

    def create(
        self,
        username: str,
        email: str = "",
        password: Optional[str] = None,
        role: str = UserRole.MEMBER,
        **extra_fields,
    ) -> User:
        user = User(username=username, email=email, role=role, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user


class ProjectRepository:
    """Репозиторий для изоляции direct ORM-запросов к сущности Project."""

    def get_all(self) -> QuerySet[Project]:
        return Project.objects.all()

    def get_by_id(self, project_id: int) -> Optional[Project]:
        return Project.objects.filter(id=project_id).first()

    def get_by_owner(self, owner: User) -> QuerySet[Project]:
        return Project.objects.filter(owner=owner)

    def create(
        self, name: str, owner: User, description: Optional[str] = None
    ) -> Project:
        return Project.objects.create(name=name, owner=owner, description=description)

    def update(self, project: Project, **kwargs) -> Project:
        for field, value in kwargs.items():
            setattr(project, field, value)
        project.save()
        return project

    def delete(self, project: Project) -> None:
        project.delete()

    def exists_by_id(self, project_id: int) -> bool:
        return Project.objects.filter(id=project_id).exists()


class TaskRepository:
    """Репозиторий для изоляции direct ORM-запросов к сущности Task."""

    def get_all(self) -> QuerySet[Task]:
        return Task.objects.all()

    def get_by_id(self, task_id: int) -> Optional[Task]:
        return Task.objects.filter(id=task_id).first()

    def get_by_project(self, project: Project | int) -> QuerySet[Task]:
        if isinstance(project, Project):
            return Task.objects.filter(project=project)
        return Task.objects.filter(project_id=project)

    def get_by_assignee(self, assignee: User | int) -> QuerySet[Task]:
        if isinstance(assignee, User):
            return Task.objects.filter(assignee=assignee)
        return Task.objects.filter(assignee_id=assignee)

    def get_by_status(self, status: str) -> QuerySet[Task]:
        return Task.objects.filter(status=status)

    def create(
        self,
        title: str,
        project: Project,
        description: Optional[str] = None,
        status: str = TaskStatus.TODO,
        priority: str = TaskPriority.MEDIUM,
        assignee: Optional[User] = None,
        due_date=None,
    ) -> Task:
        return Task.objects.create(
            title=title,
            project=project,
            description=description,
            status=status,
            priority=priority,
            assignee=assignee,
            due_date=due_date,
        )

    def update(self, task: Task, **kwargs) -> Task:
        for field, value in kwargs.items():
            setattr(task, field, value)
        task.save()
        return task

    def delete(self, task: Task) -> None:
        task.delete()

    def exists_by_id(self, task_id: int) -> bool:
        return Task.objects.filter(id=task_id).exists()
