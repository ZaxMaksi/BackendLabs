from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.tasks.models import TaskPriority, TaskStatus, User, UserRole
from apps.tasks.repositories import ProjectRepository, TaskRepository, UserRepository
from apps.tasks.services import (
    EntityNotFoundError,
    HealthCheckService,
    ProjectService,
    TaskService,
    ValidationError,
)


class HealthCheckEndpointTest(TestCase):
    """Тестирование служебного эндпоинта health-check."""

    def setUp(self):
        self.client = APIClient()

    def test_health_check_endpoint(self):
        # Тестируем доступ по прямым и вложенным URL
        for path in ["/health", "/health/", "/api/health", "/api/health/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.json(), {"status": "ok"})

    def test_health_check_service(self):
        result = HealthCheckService.check_health()
        self.assertEqual(result, {"status": "ok"})


class ModelsAndRepositoriesTest(TestCase):
    """Тестирование моделей и репозиторного слоя."""

    def setUp(self):
        self.user_repo = UserRepository()
        self.project_repo = ProjectRepository()
        self.task_repo = TaskRepository()

        self.user = self.user_repo.create(
            username="testuser",
            email="test@example.com",
            password="securepassword123",
            role=UserRole.PROJECT_MANAGER,
        )

    def test_user_creation_and_role(self):
        self.assertEqual(self.user.role, UserRole.PROJECT_MANAGER)
        self.assertTrue(self.user.check_password("securepassword123"))
        found = self.user_repo.get_by_username("testuser")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.user.id)

    def test_project_repository_crud(self):
        # Create
        project = self.project_repo.create(
            name="Main Platform",
            owner=self.user,
            description="Main project description",
        )
        self.assertEqual(project.name, "Main Platform")
        self.assertEqual(project.owner, self.user)
        self.assertEqual(str(project), "Main Platform")

        # Read
        fetched = self.project_repo.get_by_id(project.id)
        self.assertEqual(fetched.name, "Main Platform")
        self.assertTrue(self.project_repo.exists_by_id(project.id))

        owner_projects = self.project_repo.get_by_owner(self.user)
        self.assertEqual(owner_projects.count(), 1)

        # Update
        updated = self.project_repo.update(project, name="Updated Platform")
        self.assertEqual(updated.name, "Updated Platform")

        # Delete
        self.project_repo.delete(project)
        self.assertIsNone(self.project_repo.get_by_id(project.id))

    def test_task_repository_crud(self):
        project = self.project_repo.create(name="Task Project", owner=self.user)
        task = self.task_repo.create(
            title="Setup database",
            project=project,
            description="Initial setup",
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            assignee=self.user,
        )

        self.assertEqual(task.title, "Setup database")
        self.assertEqual(task.status, TaskStatus.TODO)
        self.assertEqual(task.priority, TaskPriority.HIGH)
        self.assertEqual(str(task), "Setup database")

        # Read
        fetched = self.task_repo.get_by_id(task.id)
        self.assertEqual(fetched.title, "Setup database")
        self.assertEqual(self.task_repo.get_by_project(project).count(), 1)
        self.assertEqual(self.task_repo.get_by_assignee(self.user).count(), 1)
        self.assertEqual(self.task_repo.get_by_status(TaskStatus.TODO).count(), 1)

        # Update
        self.task_repo.update(task, status=TaskStatus.IN_PROGRESS)
        self.assertEqual(
            self.task_repo.get_by_id(task.id).status, TaskStatus.IN_PROGRESS
        )

        # Delete
        self.task_repo.delete(task)
        self.assertIsNone(self.task_repo.get_by_id(task.id))


class ServicesTest(TestCase):
    """Тестирование сервисного слоя и бизнес-логики."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="serviceuser",
            email="service@example.com",
            role=UserRole.ADMIN,
        )
        self.project_service = ProjectService()
        self.task_service = TaskService()

    def test_project_service_validation_and_creation(self):
        # Валидация пустого названия
        with self.assertRaises(ValidationError):
            self.project_service.create_project(name="  ", owner=self.user)

        # Успешное создание
        project = self.project_service.create_project(
            name="Service Project", owner=self.user, description="Description"
        )
        self.assertEqual(project.name, "Service Project")

        # Получение
        retrieved = self.project_service.get_project(project.id)
        self.assertEqual(retrieved.id, project.id)

        # Несуществующий проект
        with self.assertRaises(EntityNotFoundError):
            self.project_service.get_project(999999)

    def test_task_service_validation_and_lifecycle(self):
        project = self.project_service.create_project(name="Proj", owner=self.user)

        # Ошибка при пустом заголовке
        with self.assertRaises(ValidationError):
            self.task_service.create_task(title="", project_id=project.id)

        # Ошибка при несуществующем проекте
        with self.assertRaises(EntityNotFoundError):
            self.task_service.create_task(title="Task 1", project_id=999999)

        # Ошибка при некорректном статусе
        with self.assertRaises(ValidationError):
            self.task_service.create_task(
                title="Task 1", project_id=project.id, status="invalid_status"
            )

        # Ошибка при некорректном приоритете
        with self.assertRaises(ValidationError):
            self.task_service.create_task(
                title="Task 1", project_id=project.id, priority="ultra_high"
            )

        # Успешное создание
        task = self.task_service.create_task(
            title="Clean Architecture",
            project_id=project.id,
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            assignee=self.user,
        )
        self.assertEqual(task.title, "Clean Architecture")

        # Смена статуса
        updated_task = self.task_service.change_task_status(task.id, TaskStatus.DONE)
        self.assertEqual(updated_task.status, TaskStatus.DONE)

        # Назначение исполнителя
        assigned_task = self.task_service.assign_task(task.id, None)
        self.assertIsNone(assigned_task.assignee)
