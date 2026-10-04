from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.tasks.models import Project, Task, TaskPriority, TaskStatus, User, UserRole
from apps.tasks.repositories import ProjectRepository, TaskRepository, UserRepository
from apps.tasks.services import (
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
