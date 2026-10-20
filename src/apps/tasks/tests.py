import os
import shutil
import tempfile
import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.tasks.models import (
    Attachment,
    Project,
    Task,
    TaskPriority,
    TaskStatus,
    User,
    UserRole,
)
from apps.tasks.repositories import (
    AttachmentRepository,
    ProjectRepository,
    TaskRepository,
    UserRepository,
)
from apps.tasks.services import (
    AttachmentService,
    EntityNotFoundError,
    HealthCheckService,
    ProjectService,
    TaskService,
    ValidationError,
)


class HealthCheckEndpointTest(TestCase):
    """Тестування службового ендпоінта health-check."""

    def setUp(self):
        self.client = APIClient()

    def test_health_check_endpoint(self):
        for path in ["/health", "/health/", "/api/health", "/api/health/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.json(), {"status": "ok"})

    def test_health_check_service(self):
        result = HealthCheckService.check_health()
        self.assertEqual(result, {"status": "ok"})


class ModelsAndRepositoriesTest(TestCase):
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

    def test_attachment_repository_crud(self):
        project = self.project_repo.create(name="Attach Repo Project", owner=self.user)
        task = self.task_repo.create(title="Attach Repo Task", project=project)
        temp_media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=temp_media):
                att_repo = AttachmentRepository()
                test_file = SimpleUploadedFile(
                    "readme.txt", b"Test file content", content_type="text/plain"
                )
                att = att_repo.create(
                    task=task,
                    file=test_file,
                    file_size=17,
                    content_type="text/plain",
                )
                self.assertEqual(att.task, task)
                self.assertEqual(att.file_size, 17)
                self.assertEqual(att.content_type, "text/plain")
                self.assertTrue(att_repo.exists_by_id(att.id))
                self.assertEqual(att_repo.get_by_task(task.id).count(), 1)
                self.assertIsNotNone(att_repo.get_by_id(att.id))

                # Delete
                att_repo.delete(att)
                self.assertFalse(att_repo.exists_by_id(att.id))
                self.assertIsNone(att_repo.get_by_id(att.id))
        finally:
            shutil.rmtree(temp_media, ignore_errors=True)


class ServicesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="serviceuser",
            email="service@example.com",
            role=UserRole.ADMIN,
        )
        self.project_service = ProjectService()
        self.task_service = TaskService()

    def test_project_service_validation_and_creation(self):
        # Валідація порожньої назви
        with self.assertRaises(ValidationError):
            self.project_service.create_project(name="  ", owner=self.user)

        # Успішне створення
        project = self.project_service.create_project(
            name="Service Project", owner=self.user, description="Description"
        )
        self.assertEqual(project.name, "Service Project")

        # Отримання
        retrieved = self.project_service.get_project(project.id)
        self.assertEqual(retrieved.id, project.id)

        # Неіснуючий проєкт
        with self.assertRaises(EntityNotFoundError):
            self.project_service.get_project(999999)

    def test_task_service_validation_and_lifecycle(self):
        project = self.project_service.create_project(name="Proj", owner=self.user)

        # Помилка при порожньому заголовку
        with self.assertRaises(ValidationError):
            self.task_service.create_task(title="", project_id=project.id)

        # Помилка при неіснуючому проєкті
        with self.assertRaises(EntityNotFoundError):
            self.task_service.create_task(title="Task 1", project_id=999999)

        # Помилка при некоректному статусі
        with self.assertRaises(ValidationError):
            self.task_service.create_task(
                title="Task 1", project_id=project.id, status="invalid_status"
            )

        # Помилка при некоректному пріоритеті
        with self.assertRaises(ValidationError):
            self.task_service.create_task(
                title="Task 1", project_id=project.id, priority="ultra_high"
            )

        # Помилка при даті в минулому
        with self.assertRaises(ValidationError):
            self.task_service.create_task(
                title="Task Past",
                project_id=project.id,
                due_date=timezone.now() - timedelta(days=1),
            )

        # Успішне створення
        task = self.task_service.create_task(
            title="Clean Architecture",
            project_id=project.id,
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            assignee=self.user,
        )
        self.assertEqual(task.title, "Clean Architecture")

        # Зміна статусу
        updated_task = self.task_service.change_task_status(task.id, TaskStatus.DONE)
        self.assertEqual(updated_task.status, TaskStatus.DONE)

        # Призначення виконавця
        assigned_task = self.task_service.assign_task(task.id, None)
        self.assertIsNone(assigned_task.assignee)

    def test_attachment_service_validation(self):
        att_service = AttachmentService()

        # Помилка: відсутній файл
        with self.assertRaises(ValidationError):
            att_service.validate_file(None)

        # Помилка: порожній файл
        empty_file = SimpleUploadedFile("empty.txt", b"", content_type="text/plain")
        with self.assertRaises(ValidationError):
            att_service.validate_file(empty_file)

        # Помилка: недозволене розширення
        bad_ext = SimpleUploadedFile(
            "script.sh", b"#!/bin/bash", content_type="text/plain"
        )
        with self.assertRaises(ValidationError):
            att_service.validate_file(bad_ext)

        # Помилка: недозволений MIME тип
        bad_mime = SimpleUploadedFile(
            "file.txt", b"hello", content_type="application/x-sh"
        )
        with self.assertRaises(ValidationError):
            att_service.validate_file(bad_mime)


class ProjectAPITestCase(TestCase):
    """Інтеграційні тести CRUD для ендпоінта /api/projects/."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="project_owner",
            email="owner@example.com",
            role=UserRole.PROJECT_MANAGER,
        )

    def test_project_crud_lifecycle(self):
        # 1. CREATE (POST /api/projects/)
        create_payload = {
            "name": "E-Commerce System",
            "description": "Online shop backend",
            "owner": self.user.id,
        }
        res_create = self.client.post("/api/projects/", create_payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        project_id = res_create.json()["id"]
        self.assertEqual(res_create.json()["name"], "E-Commerce System")
        self.assertEqual(res_create.json()["owner"]["id"], self.user.id)
        self.assertEqual(res_create.json()["tasks"], [])

        # 2. LIST (GET /api/projects/)
        res_list = self.client.get("/api/projects/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertIn("results", res_list.json())
        self.assertEqual(res_list.json()["count"], 1)

        # 3. RETRIEVE (GET /api/projects/{id}/)
        res_get = self.client.get(f"/api/projects/{project_id}/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.json()["id"], project_id)
        self.assertEqual(res_get.json()["owner"]["username"], "project_owner")

        # 4. UPDATE (PUT /api/projects/{id}/)
        put_payload = {
            "name": "E-Commerce Platform",
            "description": "Updated shop description",
            "owner": self.user.id,
        }
        res_put = self.client.put(
            f"/api/projects/{project_id}/", put_payload, format="json"
        )
        self.assertEqual(res_put.status_code, status.HTTP_200_OK)
        self.assertEqual(res_put.json()["name"], "E-Commerce Platform")

        # 5. PARTIAL UPDATE (PATCH /api/projects/{id}/)
        patch_payload = {"name": "E-Commerce Final"}
        res_patch = self.client.patch(
            f"/api/projects/{project_id}/", patch_payload, format="json"
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.json()["name"], "E-Commerce Final")

        # 6. DELETE (DELETE /api/projects/{id}/)
        res_delete = self.client.delete(f"/api/projects/{project_id}/")
        self.assertEqual(res_delete.status_code, status.HTTP_204_NO_CONTENT)

        # 7. VERIFY NOT FOUND
        res_deleted = self.client.get(f"/api/projects/{project_id}/")
        self.assertEqual(res_deleted.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_deleted.json()["title"], "Not Found")


class TaskAPITestCase(TestCase):
    """Інтеграційні тести CRUD та зв'язків для ендпоінта /api/tasks/."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="task_assignee",
            email="assignee@example.com",
            role=UserRole.MEMBER,
        )
        self.project = Project.objects.create(
            name="Alpha Project",
            owner=self.user,
            description="Alpha description",
        )

    def test_task_crud_and_nested_relations(self):
        due_future = timezone.now() + timedelta(days=5)

        # 1. CREATE (POST /api/tasks/)
        create_payload = {
            "title": "Design REST API",
            "description": "Implement CRUD and RFC 7807",
            "status": "todo",
            "priority": "high",
            "project": self.project.id,
            "assignee": self.user.id,
            "due_date": due_future.isoformat(),
        }
        res_create = self.client.post("/api/tasks/", create_payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        data = res_create.json()
        task_id = data["id"]
        self.assertEqual(data["title"], "Design REST API")
        self.assertEqual(data["status"], "todo")
        self.assertEqual(data["priority"], "high")

        # Перевірка зв'язків та вкладених даних (One-to-Many)
        self.assertEqual(data["project"]["id"], self.project.id)
        self.assertEqual(data["project"]["name"], "Alpha Project")
        self.assertEqual(data["assignee"]["id"], self.user.id)
        self.assertEqual(data["assignee"]["username"], "task_assignee")

        # Перевірка вкладених tasks при запиті проєкту
        res_project = self.client.get(f"/api/projects/{self.project.id}/")
        self.assertEqual(res_project.status_code, status.HTTP_200_OK)
        project_tasks = res_project.json()["tasks"]
        self.assertEqual(len(project_tasks), 1)
        self.assertEqual(project_tasks[0]["id"], task_id)
        self.assertEqual(project_tasks[0]["title"], "Design REST API")

        # 2. LIST (GET /api/tasks/)
        res_list = self.client.get("/api/tasks/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(res_list.json()["count"], 1)

        # 3. RETRIEVE (GET /api/tasks/{id}/)
        res_get = self.client.get(f"/api/tasks/{task_id}/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.json()["id"], task_id)

        # 4. UPDATE (PUT /api/tasks/{id}/)
        put_payload = {
            "title": "Design and Review REST API",
            "description": "Updated description",
            "status": "in_progress",
            "priority": "medium",
            "project": self.project.id,
            "assignee": self.user.id,
            "due_date": (timezone.now() + timedelta(days=7)).isoformat(),
        }
        res_put = self.client.put(f"/api/tasks/{task_id}/", put_payload, format="json")
        self.assertEqual(res_put.status_code, status.HTTP_200_OK)
        self.assertEqual(res_put.json()["title"], "Design and Review REST API")
        self.assertEqual(res_put.json()["status"], "in_progress")

        # 5. PARTIAL UPDATE (PATCH /api/tasks/{id}/)
        patch_payload = {"status": "done"}
        res_patch = self.client.patch(
            f"/api/tasks/{task_id}/", patch_payload, format="json"
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.json()["status"], "done")

        # 6. DELETE (DELETE /api/tasks/{id}/)
        res_delete = self.client.delete(f"/api/tasks/{task_id}/")
        self.assertEqual(res_delete.status_code, status.HTTP_204_NO_CONTENT)

        # 7. VERIFY NOT FOUND
        res_deleted = self.client.get(f"/api/tasks/{task_id}/")
        self.assertEqual(res_deleted.status_code, status.HTTP_404_NOT_FOUND)


class QueryOptimizationNPlusOneTest(TestCase):
    """Тестування усунення проблеми N+1 за допомогою select_related та prefetch_related."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="owner_user", email="owner@test.com"
        )
        self.assignee1 = User.objects.create_user(
            username="worker1", email="worker1@test.com"
        )
        self.assignee2 = User.objects.create_user(
            username="worker2", email="worker2@test.com"
        )

        # Створюємо 3 проєкти та по 4 завдання у кожному
        for p_idx in range(3):
            proj = Project.objects.create(name=f"Project {p_idx}", owner=self.owner)
            for t_idx in range(4):
                assignee = self.assignee1 if t_idx % 2 == 0 else self.assignee2
                Task.objects.create(
                    title=f"Task {p_idx}_{t_idx}",
                    project=proj,
                    assignee=assignee,
                    status=TaskStatus.TODO,
                    priority=TaskPriority.MEDIUM,
                )

    def test_repository_tasks_no_n_plus_one(self):
        task_repo = TaskRepository()
        # При вибірці всіх завдань та зверненні до task.project, task.project.owner, task.assignee
        # має виконуватися рівно 1 SQL-запит завдяки select_related
        with self.assertNumQueries(1):
            tasks = list(task_repo.get_all())
            self.assertEqual(len(tasks), 12)
            for task in tasks:
                _ = task.project.name
                _ = task.project.owner.username
                _ = task.assignee.username

    def test_repository_projects_no_n_plus_one(self):
        project_repo = ProjectRepository()
        # 1 запит для projects з owner + 1 запит для prefetch_related tasks з assignee
        with self.assertNumQueries(2):
            projects = list(project_repo.get_all())
            self.assertEqual(len(projects), 3)
            for project in projects:
                _ = project.owner.username
                for task in project.tasks.all():
                    _ = task.title
                    _ = task.assignee.username

    def test_tasks_list_endpoint_queries(self):
        # 1 запит COUNT (пагінація) + 1 запит із JOIN-ами (select_related) = 2 запити
        with self.assertNumQueries(2):
            response = self.client.get("/api/tasks/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.json()["count"], 12)

    def test_projects_list_endpoint_queries(self):
        # 1 запит COUNT (пагінація) + 1 запит projects + 1 запит prefetch tasks = 3 запити
        with self.assertNumQueries(3):
            response = self.client.get("/api/projects/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.json()["count"], 3)


class PaginationFilteringSortingTest(TestCase):
    """Тестування пагінації (?page=), фільтрації (?status=) та сортування (?ordering=)."""

    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(username="alice", email="alice@test.com")
        self.user2 = User.objects.create_user(username="bob", email="bob@test.com")
        self.project1 = Project.objects.create(name="Beta Project", owner=self.user1)
        self.project2 = Project.objects.create(name="Gamma Project", owner=self.user2)

        base_time = timezone.now()
        self.task1 = Task.objects.create(
            title="Task A",
            project=self.project1,
            assignee=self.user1,
            status=TaskStatus.TODO,
            priority=TaskPriority.LOW,
            due_date=base_time + timedelta(days=1),
        )
        self.task2 = Task.objects.create(
            title="Task B",
            project=self.project1,
            assignee=self.user2,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            due_date=base_time + timedelta(days=3),
        )
        self.task3 = Task.objects.create(
            title="Task C",
            project=self.project2,
            assignee=self.user1,
            status=TaskStatus.DONE,
            priority=TaskPriority.MEDIUM,
            due_date=base_time + timedelta(days=2),
        )

    def test_pagination(self):
        response = self.client.get("/api/tasks/?page=1&page_size=2")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 2)
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

        # Друга сторінка
        response_page2 = self.client.get("/api/tasks/?page=2&page_size=2")
        self.assertEqual(response_page2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_page2.json()["results"]), 1)

    def test_filter_by_status(self):
        response = self.client.get("/api/tasks/?status=in_progress")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.task2.id)

    def test_filter_by_priority(self):
        response = self.client.get("/api/tasks/?priority=high")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.task2.id)

    def test_filter_by_project_id(self):
        response = self.client.get(f"/api/tasks/?project_id={self.project2.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.task3.id)

    def test_filter_by_assignee_id(self):
        response = self.client.get(f"/api/tasks/?assignee_id={self.user2.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.task2.id)

    def test_sorting(self):
        # Сортування за зростанням due_date (task1 < task3 < task2)
        response = self.client.get("/api/tasks/?ordering=due_date")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [self.task1.id, self.task3.id, self.task2.id])

        # Сортування за спаданням due_date
        response_desc = self.client.get("/api/tasks/?ordering=-due_date")
        self.assertEqual(response_desc.status_code, status.HTTP_200_OK)
        ids_desc = [item["id"] for item in response_desc.json()["results"]]
        self.assertEqual(ids_desc, [self.task2.id, self.task3.id, self.task1.id])


class ValidationAndRFC7807ErrorTest(TestCase):
    """Тестування валідації даних та формату відповідей про помилки RFC 7807."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="val_user", email="val@test.com")
        self.project = Project.objects.create(name="Val Project", owner=self.user)

    def test_validation_empty_task_title_rfc_7807(self):
        payload = {
            "title": "   ",
            "project": self.project.id,
        }
        response = self.client.post("/api/tasks/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:unprocessable-entity")
        self.assertEqual(data["title"], "Unprocessable Entity")
        self.assertEqual(data["status"], 422)
        self.assertIn("detail", data)
        self.assertEqual(data["instance"], "/api/tasks/")
        self.assertIn("invalid_params", data)
        self.assertIn("title", data["invalid_params"])

    def test_validation_past_due_date_rfc_7807(self):
        past_date = (timezone.now() - timedelta(days=2)).isoformat()
        payload = {
            "title": "Past Task",
            "project": self.project.id,
            "due_date": past_date,
        }
        response = self.client.post("/api/tasks/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data["status"], 422)
        self.assertIn("due_date", data["invalid_params"])

    def test_validation_invalid_choice_status_rfc_7807(self):
        payload = {
            "title": "Invalid Status Task",
            "project": self.project.id,
            "status": "not_a_valid_status",
        }
        response = self.client.post("/api/tasks/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data["status"], 422)
        self.assertIn("status", data["invalid_params"])

    def test_validation_empty_project_name_rfc_7807(self):
        payload = {"name": "   ", "owner": self.user.id}
        response = self.client.post("/api/projects/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:unprocessable-entity")
        self.assertEqual(data["status"], 422)
        self.assertIn("name", data["invalid_params"])

    def test_not_found_rfc_7807(self):
        response = self.client.get("/api/tasks/999999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:not-found")
        self.assertEqual(data["title"], "Not Found")
        self.assertEqual(data["status"], 404)
        self.assertEqual(data["instance"], "/api/tasks/999999/")
        self.assertIn("detail", data)

    def test_method_not_allowed_rfc_7807(self):
        # GET на /health дозволено, POST не дозволено
        response = self.client.post("/api/health/")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:method-not-allowed")
        self.assertEqual(data["status"], 405)
        self.assertIn("detail", data)


class OpenAPIDocumentationTest(TestCase):
    """Інтеграційні тести для OpenAPI v3 специфікації та Swagger UI / Redoc."""

    def setUp(self):
        self.client = APIClient()

    def test_openapi_schema_yaml(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("openapi: 3.0", response.content.decode("utf-8"))
        self.assertIn("Task Tracker API", response.content.decode("utf-8"))

    def test_openapi_schema_json(self):
        response = self.client.get("/api/schema/?format=json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("openapi", data)
        self.assertIn("info", data)
        self.assertEqual(data["info"]["title"], "Task Tracker API")
        self.assertIn("paths", data)
        # Перевірка наявності ключових шляхів
        self.assertIn("/api/projects/", data["paths"])
        self.assertIn("/api/tasks/", data["paths"])
        self.assertIn("/api/attachments/", data["paths"])
        self.assertIn("/api/health/", data["paths"])

    def test_swagger_ui_endpoint(self):
        response = self.client.get("/api/schema/swagger-ui/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("swagger-ui", response.content.decode("utf-8").lower())

    def test_redoc_endpoint(self):
        response = self.client.get("/api/schema/redoc/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("redoc", response.content.decode("utf-8").lower())


class AttachmentAPITestCase(TestCase):
    """Інтеграційні тести завантаження, видачі та валідації файлів-вкладень."""

    def setUp(self):
        self.client = APIClient()
        self.temp_dir = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_dir)
        self.settings_override.enable()

        self.user = User.objects.create_user(
            username="attach_user", email="attach@test.com"
        )
        self.project = Project.objects.create(name="Attach Project", owner=self.user)
        self.task1 = Task.objects.create(
            title="Attachment Task 1",
            project=self.project,
            assignee=self.user,
        )
        self.task2 = Task.objects.create(
            title="Attachment Task 2",
            project=self.project,
            assignee=self.user,
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_upload_valid_pdf_attachment(self):
        # 1. Запит: завантаження валідного PDF
        pdf_bytes = b"%PDF-1.4 test file content for document"
        uploaded_file = SimpleUploadedFile(
            "document.pdf", pdf_bytes, content_type="application/pdf"
        )
        response = self.client.post(
            "/api/attachments/",
            {"task": self.task1.id, "file": uploaded_file},
            format="multipart",
        )

        # 2. Відповідь: 201 Created та структура
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        attachment_id = data["id"]
        self.assertEqual(data["task"], self.task1.id)
        self.assertEqual(data["file_size"], len(pdf_bytes))
        self.assertEqual(data["content_type"], "application/pdf")
        self.assertIn("uploaded_at", data)
        self.assertIn("document", data["file"])

        # 3. Стан БД: пряма перевірка запису в базі даних
        att_db = Attachment.objects.filter(id=attachment_id).first()
        self.assertIsNotNone(att_db)
        self.assertEqual(att_db.task_id, self.task1.id)
        self.assertEqual(att_db.file_size, len(pdf_bytes))
        self.assertEqual(att_db.content_type, "application/pdf")
        self.assertTrue(os.path.exists(att_db.file.path))

    def test_upload_valid_png_attachment(self):
        png_bytes = b"\x89PNG\r\n\x1a\nsamplepngcontent"
        uploaded_file = SimpleUploadedFile(
            "screenshot.png", png_bytes, content_type="image/png"
        )
        response = self.client.post(
            "/api/attachments/",
            {"task_id": self.task1.id, "file": uploaded_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["content_type"], "image/png")

        # Перевірка в БД
        self.assertTrue(Attachment.objects.filter(id=data["id"]).exists())

    def test_upload_attachment_via_task_nested_endpoint(self):
        # Завантаження безпосередньо через ендпоінт задачі /api/tasks/{task_id}/attachments/
        txt_bytes = b"Text file attachment content"
        uploaded_file = SimpleUploadedFile(
            "notes.txt", txt_bytes, content_type="text/plain"
        )
        response = self.client.post(
            f"/api/tasks/{self.task1.id}/attachments/",
            {"file": uploaded_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["task"], self.task1.id)
        self.assertEqual(data["file_size"], len(txt_bytes))

        # Перевірка в БД
        att_db = Attachment.objects.get(id=data["id"])
        self.assertEqual(att_db.task_id, self.task1.id)

    def test_list_and_filter_attachments(self):
        # Додаємо 2 вкладення до task1 і 1 до task2
        f1 = SimpleUploadedFile("doc1.pdf", b"%PDF-1", content_type="application/pdf")
        f2 = SimpleUploadedFile("doc2.txt", b"notes", content_type="text/plain")
        f3 = SimpleUploadedFile("doc3.png", b"\x89PNG", content_type="image/png")

        self.client.post(
            "/api/attachments/", {"task": self.task1.id, "file": f1}, format="multipart"
        )
        self.client.post(
            "/api/attachments/", {"task": self.task1.id, "file": f2}, format="multipart"
        )
        self.client.post(
            "/api/attachments/", {"task": self.task2.id, "file": f3}, format="multipart"
        )

        # 1. Запит всіх вкладень
        res_all = self.client.get("/api/attachments/")
        self.assertEqual(res_all.status_code, status.HTTP_200_OK)
        self.assertEqual(res_all.json()["count"], 3)

        # 2. Фільтрація за task_id через query-параметр
        res_task1 = self.client.get(f"/api/attachments/?task_id={self.task1.id}")
        self.assertEqual(res_task1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_task1.json()["count"], 2)

        # 3. Отримання списку через nested-action задачі
        res_nested = self.client.get(f"/api/tasks/{self.task1.id}/attachments/")
        self.assertEqual(res_nested.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_nested.json()), 2)

    def test_download_attachment(self):
        content = b"Binary attachment payload to download"
        uploaded_file = SimpleUploadedFile(
            "manual.txt", content, content_type="text/plain"
        )
        res_upload = self.client.post(
            "/api/attachments/",
            {"task": self.task1.id, "file": uploaded_file},
            format="multipart",
        )
        att_id = res_upload.json()["id"]

        # Скачування файлу
        res_download = self.client.get(f"/api/attachments/{att_id}/download/")
        self.assertEqual(res_download.status_code, status.HTTP_200_OK)
        self.assertIn(
            "attachment; filename=", res_download.headers.get("Content-Disposition", "")
        )
        self.assertIn("manual.txt", res_download.headers.get("Content-Disposition", ""))
        self.assertEqual(res_download.headers.get("Content-Type"), "text/plain")
        self.assertEqual(b"".join(res_download.streaming_content), content)

    def test_delete_attachment_full_lifecycle(self):
        uploaded_file = SimpleUploadedFile(
            "to_delete.txt", b"Delete me", content_type="text/plain"
        )
        res_upload = self.client.post(
            "/api/attachments/",
            {"task": self.task1.id, "file": uploaded_file},
            format="multipart",
        )
        att_id = res_upload.json()["id"]
        att_db = Attachment.objects.get(id=att_id)
        file_path = att_db.file.path
        self.assertTrue(os.path.exists(file_path))

        # 1. Запит на видалення (DELETE /api/attachments/{id}/)
        res_delete = self.client.delete(f"/api/attachments/{att_id}/")
        self.assertEqual(res_delete.status_code, status.HTTP_204_NO_CONTENT)

        # 2. Перевірка БД: запис видалено
        self.assertFalse(Attachment.objects.filter(id=att_id).exists())

        # 3. Перевірка 404 при повторному зверненні
        res_get = self.client.get(f"/api/attachments/{att_id}/")
        self.assertEqual(res_get.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_file_exceeding_max_size_rfc_7807(self):
        # Ліміт 10 МБ, створюємо файл 10 МБ + 1024 байти
        large_bytes = b"0" * (10 * 1024 * 1024 + 1024)
        large_file = SimpleUploadedFile(
            "huge.pdf", large_bytes, content_type="application/pdf"
        )
        response = self.client.post(
            "/api/attachments/",
            {"task": self.task1.id, "file": large_file},
            format="multipart",
        )

        # Перевірка RFC 7807 помилки
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:unprocessable-entity")
        self.assertEqual(data["status"], 422)
        self.assertIn("exceeds limit", data["detail"])

        # Перевірка стану БД: жодного вкладення не створено
        self.assertEqual(Attachment.objects.count(), 0)

    def test_upload_file_invalid_extension_rfc_7807(self):
        bad_file = SimpleUploadedFile(
            "virus.exe", b"MZexecutablebytes", content_type="application/octet-stream"
        )
        response = self.client.post(
            "/api/attachments/",
            {"task": self.task1.id, "file": bad_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data["status"], 422)
        self.assertIn("extension", data["detail"].lower())
        self.assertEqual(Attachment.objects.count(), 0)

    def test_upload_file_invalid_mime_type_rfc_7807(self):
        bad_file = SimpleUploadedFile(
            "script.txt", b"#!/bin/bash\nrm -rf /", content_type="application/x-sh"
        )
        response = self.client.post(
            "/api/attachments/",
            {"task": self.task1.id, "file": bad_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data["status"], 422)
        self.assertIn("mime type", data["detail"].lower())
        self.assertEqual(Attachment.objects.count(), 0)

    def test_upload_empty_file_rfc_7807(self):
        empty_file = SimpleUploadedFile(
            "empty.pdf", b"", content_type="application/pdf"
        )
        response = self.client.post(
            "/api/attachments/",
            {"task": self.task1.id, "file": empty_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertEqual(data["status"], 422)
        self.assertEqual(Attachment.objects.count(), 0)


class FullLifecycleIntegrationTest(TestCase):
    """
    Інтеграційні тести повного циклу ключових сценаріїв:
    Створення ресурсу → Перевірка коду відповіді → Перевірка змін безпосередньо у БД (ланцюжок: запит → відповідь → стан БД).
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="lifecycle_user",
            email="lifecycle@test.com",
            role=UserRole.PROJECT_MANAGER,
        )

    def test_project_lifecycle_chain(self):
        # 1. Запит на створення (POST)
        payload = {
            "name": "Integration Project",
            "description": "Integration testing project",
            "owner": self.user.id,
        }
        res_post = self.client.post("/api/projects/", payload, format="json")

        # 2. Перевірка відповіді: 201 Created
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        proj_id = res_post.json()["id"]

        # 3. Перевірка стану БД безпосередньо через Django ORM
        proj_db = Project.objects.filter(id=proj_id).first()
        self.assertIsNotNone(proj_db)
        self.assertEqual(proj_db.name, "Integration Project")
        self.assertEqual(proj_db.owner_id, self.user.id)

        # 4. Запит на оновлення (PATCH)
        res_patch = self.client.patch(
            f"/api/projects/{proj_id}/",
            {"name": "Integration Project Updated"},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)

        # 5. Перевірка змін безпосередньо у БД
        proj_db.refresh_from_db()
        self.assertEqual(proj_db.name, "Integration Project Updated")

        # 6. Запит на видалення (DELETE)
        res_del = self.client.delete(f"/api/projects/{proj_id}/")
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)

        # 7. Перевірка видалення у БД
        self.assertFalse(Project.objects.filter(id=proj_id).exists())

    def test_task_lifecycle_chain(self):
        project = Project.objects.create(name="Task Lifecycle Proj", owner=self.user)
        due = timezone.now() + timedelta(days=10)

        # 1. Запит на створення завдання (POST)
        task_payload = {
            "title": "Build Integration Tests",
            "description": "Cover stage 3 requirements",
            "project": project.id,
            "assignee": self.user.id,
            "status": "todo",
            "priority": "high",
            "due_date": due.isoformat(),
        }
        res_post = self.client.post("/api/tasks/", task_payload, format="json")

        # 2. Перевірка коду відповіді: 201 Created
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        task_id = res_post.json()["id"]

        # 3. Перевірка стану безпосередньо у БД
        task_db = Task.objects.filter(id=task_id).first()
        self.assertIsNotNone(task_db)
        self.assertEqual(task_db.title, "Build Integration Tests")
        self.assertEqual(task_db.status, TaskStatus.TODO)
        self.assertEqual(task_db.priority, TaskPriority.HIGH)
        self.assertEqual(task_db.project_id, project.id)
        self.assertEqual(task_db.assignee_id, self.user.id)

        # 4. Запит на оновлення статусу (PATCH)
        res_patch = self.client.patch(
            f"/api/tasks/{task_id}/", {"status": "in_progress"}, format="json"
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)

        # 5. Перевірка оновленого стану у БД
        task_db.refresh_from_db()
        self.assertEqual(task_db.status, TaskStatus.IN_PROGRESS)

        # 6. Запит на завершення (PATCH done)
        res_done = self.client.patch(
            f"/api/tasks/{task_id}/", {"status": "done"}, format="json"
        )
        self.assertEqual(res_done.status_code, status.HTTP_200_OK)
        task_db.refresh_from_db()
        self.assertEqual(task_db.status, TaskStatus.DONE)

        # 7. Запит на видалення (DELETE)
        res_del = self.client.delete(f"/api/tasks/{task_id}/")
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)

        # 8. Перевірка у БД
        self.assertFalse(Task.objects.filter(id=task_id).exists())

    def test_cascade_delete_chain(self):
        # Перевірка каскадного видалення Проєкт → Завдання → Вкладення у БД
        temp_dir = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=temp_dir):
                proj = Project.objects.create(name="Cascade Proj", owner=self.user)
                t1 = Task.objects.create(title="Cascade Task", project=proj)
                f = SimpleUploadedFile(
                    "casc.txt", b"cascade", content_type="text/plain"
                )
                att = Attachment.objects.create(
                    task=t1, file=f, file_size=7, content_type="text/plain"
                )

                # Переконуємось, що всі сутності створені у БД
                self.assertTrue(Project.objects.filter(id=proj.id).exists())
                self.assertTrue(Task.objects.filter(id=t1.id).exists())
                self.assertTrue(Attachment.objects.filter(id=att.id).exists())

                # Видаляємо проєкт через API
                res = self.client.delete(f"/api/projects/{proj.id}/")
                self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

                # Перевіряємо каскадне видалення у БД
                self.assertFalse(Project.objects.filter(id=proj.id).exists())
                self.assertFalse(Task.objects.filter(id=t1.id).exists())
                self.assertFalse(Attachment.objects.filter(id=att.id).exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TwelveFactorAppConfigTest(TestCase):
    """Тестування конфігурації за принципами 12-Factor App та шаблону оточення."""

    def test_settings_loaded_from_environment(self):
        from django.conf import settings

        self.assertIsNotNone(settings.SECRET_KEY)
        self.assertIsInstance(settings.DEBUG, bool)
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)
        self.assertIn("default", settings.CACHES)
        self.assertIn("BACKEND", settings.CACHES["default"])
        self.assertIsNotNone(settings.EXTERNAL_API_BASE_URL)
        self.assertGreater(settings.EXTERNAL_API_TIMEOUT, 0)
        self.assertGreater(settings.BACKGROUND_TASK_MAX_WORKERS, 0)

    def test_env_example_file_structure(self):
        env_example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            ".env.example",
        )
        self.assertTrue(os.path.exists(env_example_path))
        with open(env_example_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("SECRET_KEY=", content)
        self.assertIn("DEBUG=", content)
        self.assertIn("DB_NAME=", content)
        self.assertIn("CACHE_BACKEND=", content)
        self.assertIn("EXTERNAL_API_TIMEOUT=", content)
        self.assertIn("BACKGROUND_TASK_MAX_WORKERS=", content)
        # Verify no real secrets leaked in example template
        self.assertNotIn("bmnnpg777", content)


class BackgroundTaskProcessingTest(TransactionTestCase):
    """Тестування асинхронного фонового опрацювання операцій без брокера (202 Accepted)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="bg_tester", password="secure_password"
        )
        self.project = Project.objects.create(
            name="Async Project",
            description="Testing ThreadPool background processing",
            owner=self.user,
        )
        now = timezone.now()
        # Створюємо завдання різних статусів та пріоритетів
        Task.objects.create(
            title="Task 1",
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            project=self.project,
            due_date=now - timedelta(days=2),  # Overdue
        )
        Task.objects.create(
            title="Task 2",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.MEDIUM,
            project=self.project,
            due_date=now + timedelta(days=3),  # Upcoming
        )
        Task.objects.create(
            title="Task 3",
            status=TaskStatus.DONE,
            priority=TaskPriority.LOW,
            project=self.project,
            due_date=now - timedelta(days=1),
        )

    def test_project_report_generation_returns_202_accepted(self):
        response = self.client.post(
            f"/api/projects/{self.project.id}/generate-report/"
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        data = response.json()
        self.assertEqual(data["status"], "accepted")
        self.assertIn("job_id", data)
        self.assertIn("check_status_url", data)
        self.assertIn(data["job_id"], data["check_status_url"])

        # Очікуємо завершення виконання у фоновому потоці до teardown тесту
        job_id = data["job_id"]
        for _ in range(20):
            res = self.client.get(f"/api/background-tasks/{job_id}/")
            if res.json().get("status") in ["completed", "failed"]:
                break
            time.sleep(0.05)

    def test_background_task_execution_and_status_polling(self):
        # 1. Запуск фонової задачі
        response = self.client.post(
            f"/api/projects/{self.project.id}/generate-report/"
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        job_id = response.json()["job_id"]

        # 2. Очікування завершення виконання у пулі потоків
        max_retries = 20
        task_data = None
        for _ in range(max_retries):
            res_status = self.client.get(f"/api/background-tasks/{job_id}/")
            self.assertEqual(res_status.status_code, status.HTTP_200_OK)
            task_data = res_status.json()
            if task_data["status"] in ["completed", "failed"]:
                break
            time.sleep(0.05)

        self.assertIsNotNone(task_data)
        self.assertEqual(task_data["status"], "completed")
        self.assertIsNone(task_data["error"])

        # 3. Перевірка обчислених даних аналітичного звіту
        report = task_data["result"]
        self.assertIsNotNone(report)
        self.assertEqual(report["project_id"], self.project.id)
        self.assertEqual(report["total_tasks"], 3)
        self.assertEqual(report["tasks_by_status"]["todo"], 1)
        self.assertEqual(report["tasks_by_status"]["in_progress"], 1)
        self.assertEqual(report["tasks_by_status"]["done"], 1)
        self.assertEqual(report["tasks_by_priority"]["high"], 1)
        self.assertEqual(report["overdue_tasks"], 1)
        self.assertEqual(report["upcoming_deadlines_next_7_days"], 1)
        self.assertAlmostEqual(report["completion_rate_percent"], 33.33, places=2)

    def test_background_task_not_found_rfc_7807(self):
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = self.client.get(f"/api/background-tasks/{fake_uuid}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:not-found")
        self.assertEqual(data["status"], 404)
        self.assertIn("not found", data["detail"].lower())

    def test_generate_report_non_existent_project_rfc_7807(self):
        response = self.client.post("/api/projects/999999/generate-report/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:not-found")
        self.assertEqual(data["status"], 404)


class ExternalCalendarAndCachingTest(TestCase):
    """Тестування інтеграції із зовнішнім REST-сервісом та кешуванням у пам'яті."""

    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch("requests.get")
    def test_external_holidays_successful_fetch_and_caching(self, mock_get):
        mock_holidays = [
            {"date": "2026-01-01", "localName": "Новий Рік", "name": "New Year's Day", "countryCode": "UA"},
            {"date": "2026-01-07", "localName": "Різдво", "name": "Christmas Day", "countryCode": "UA"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_holidays
        mock_get.return_value = mock_response

        # 1. Перший запит: звернення до зовнішнього API (miss кешу)
        res1 = self.client.get("/api/external/holidays/?year=2026&country_code=UA")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        data1 = res1.json()
        self.assertFalse(data1["cached"])
        self.assertEqual(data1["total_holidays"], 2)
        self.assertEqual(data1["country_code"], "UA")
        self.assertEqual(mock_get.call_count, 1)

        # 2. Другий запит: повернення з LocMemCache (hit кешу)
        res2 = self.client.get("/api/external/holidays/?year=2026&country_code=UA")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        data2 = res2.json()
        self.assertTrue(data2["cached"])
        self.assertEqual(data2["total_holidays"], 2)
        # requests.get НЕ повинен викликатися повторно
        self.assertEqual(mock_get.call_count, 1)

    @patch("requests.get")
    def test_external_holidays_timeout_rfc_7807(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out after 3.0s")
        response = self.client.get("/api/external/holidays/?year=2026&country_code=UA")
        self.assertEqual(response.status_code, status.HTTP_504_GATEWAY_TIMEOUT)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:gateway-timeout")
        self.assertEqual(data["status"], 504)
        self.assertIn("timed out", data["detail"].lower())

    @patch("requests.get")
    def test_external_holidays_connection_error_rfc_7807(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed to resolve host")
        response = self.client.get("/api/external/holidays/?year=2026&country_code=UA")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        data = response.json()
        self.assertEqual(data["type"], "urn:problem-type:service-unavailable")
        self.assertEqual(data["status"], 503)

    def test_external_holidays_invalid_parameters_rfc_7807(self):
        # Некоректний рік
        res_bad_year = self.client.get("/api/external/holidays/?year=invalid_year")
        self.assertEqual(res_bad_year.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_bad_year.json()["type"], "urn:problem-type:bad-request")

        # Некоректний код країни
        res_bad_code = self.client.get("/api/external/holidays/?country_code=TOOLONG")
        self.assertEqual(res_bad_code.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_bad_code.json()["type"], "urn:problem-type:bad-request")


class DatabaseIndexesOptimizationTest(TestCase):
    """Тестування наявності та оптимізації індексів у PostgreSQL."""

    def test_task_indexes_exist_in_postgresql(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'tasks_task';"
            )
            indexes = [row[0] for row in cursor.fetchall()]

        self.assertIn("task_status_due_date_idx", indexes)
        self.assertIn("task_status_idx", indexes)
        self.assertIn("task_due_date_idx", indexes)
        self.assertIn("task_title_idx", indexes)

    def test_task_composite_index_query_plan(self):
        user = User.objects.create_user(username="idx_user", password="password")
        project = Project.objects.create(name="Idx Project", owner=user)
        now = timezone.now()

        # Створюємо тестові записи
        tasks = [
            Task(
                title=f"Test Index Task {i}",
                status=TaskStatus.TODO if i % 2 == 0 else TaskStatus.DONE,
                priority=TaskPriority.HIGH,
                project=project,
                assignee=user,
                due_date=now + timedelta(days=i),
            )
            for i in range(50)
        ]
        Task.objects.bulk_create(tasks)

        with connection.cursor() as cursor:
            # Примусово вмикаємо використання індексів
            cursor.execute("SET enable_seqscan = off;")
            cursor.execute(
                """
                EXPLAIN (FORMAT TEXT)
                SELECT id, title, status, due_date
                FROM tasks_task
                WHERE status = 'todo' AND due_date <= NOW() + INTERVAL '5 days';
                """
            )
            plan_lines = [row[0] for row in cursor.fetchall()]
            cursor.execute("RESET enable_seqscan;")

        plan_text = " ".join(plan_lines)
        # Переконуємось, що оптимізатор PostgreSQL використовує створений індекс
        self.assertTrue(
            "task_status_due_date_idx" in plan_text or "Index Scan" in plan_text or "Bitmap Index Scan" in plan_text,
            f"Expected index scan, got plan:\n{plan_text}",
        )
