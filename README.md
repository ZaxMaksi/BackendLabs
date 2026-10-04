# Task Tracker API (Система управления задачами)

Лабораторный проект по теме 3.2 «Система управления задачами (Трекер задач)» на стеке **Python 3.10+ / Django / Django REST Framework / PostgreSQL**.

## Архитектура проекта

Проект построен по принципам многослойной архитектуры (Clean Architecture / Layered Monolith) с чётким разделением ответственности:

```text
HTTP Request
     │
     ▼
[ Views / Controllers ]  (src/apps/tasks/views.py)
     │
     ▼
[ Service Layer ]        (src/apps/tasks/services.py)  ── Бизнес-логика и валидации
     │
     ▼
[ Repository Layer ]     (src/apps/tasks/repositories.py) ── Изоляция direct ORM-запросов
     │
     ▼
[ Models / Django ORM ]  (src/apps/tasks/models.py)
     │
     ▼
[ PostgreSQL DB ]
```

### Реализованные сущности (Этап 1):
1. **`User`** (`apps.tasks.models.User`): Кастомная модель на основе `AbstractUser` с ролевой моделью (`admin`, `project_manager`, `member`).
2. **`Project`** (`apps.tasks.models.Project`): Проекты с полями `name`, `description`, `created_at` и привязкой к владельцу `owner`.
3. **`Task`** (`apps.tasks.models.Task`): Задачи с полями `title`, `description`, `status` (`todo`, `in_progress`, `done`), `priority` (`low`, `medium`, `high`), связями с проектом (`project`) и исполнителем (`assignee`), дедлайном `due_date` и датой создания `created_at`.

---

## Требования

* Python 3.10+
* PostgreSQL 14+
* Виртуальное окружение (`venv`)

---

## Установка и запуск

### 1. Клонирование репозитория и переход в проект
```bash
git clone <url_репозитория>
cd task_tracker_project
```

### 2. Создание и активация виртуального окружения
```bash
python -m venv .venv

# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# Linux / macOS:
source .venv/bin/activate
```

### 3. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения
Создайте файл `.env` в корне проекта (по шаблону):
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=task_tracker_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

### 5. Применение миграций к PostgreSQL
```bash
python manage.py migrate
```

### 6. Запуск тестов
```bash
python manage.py test apps.tasks
```

### 7. Запуск сервера разработки
```bash
python manage.py runserver
```

---

---

## Эндпоинты API (Этапы 1 и 2)

### 1. Сервисные эндпоинты
| Метод | URL | Описание | Ожидаемый ответ |
|-------|-----|----------|-----------------|
| `GET` | `/health` или `/health/` | Health-check сервиса и БД | `{"status": "ok"}` (200 OK) |
| `GET` | `/api/health/` | API-версия Health-check | `{"status": "ok"}` (200 OK) |
| `GET` | `/admin/` | Панель администратора Django | Django Admin |

### 2. Проекты (`/api/projects/`)
| Метод | URL | Описание | Статус-код |
|-------|-----|----------|------------|
| `GET` | `/api/projects/` | Список проектов (пагинация, сортировка, фильтрация) | 200 OK |
| `POST` | `/api/projects/` | Создание нового проекта | 201 Created |
| `GET` | `/api/projects/{id}/` | Детальная информация о проекте с вложенными задачами и владельцем | 200 OK |
| `PUT` | `/api/projects/{id}/` | Полное обновление проекта | 200 OK |
| `PATCH` | `/api/projects/{id}/` | Частичное обновление проекта | 200 OK |
| `DELETE` | `/api/projects/{id}/` | Удаление проекта | 204 No Content |

**Query-параметры для `/api/projects/`:**
* `?page=1&page_size=10` — пагинация (`PageNumberPagination`)
* `?owner_id=1` — фильтрация по владельцу проекта
* `?name=Alpha` — поиск/фильтрация по названию
* `?ordering=-created_at` — сортировка (`created_at`, `-created_at`, `name`, `-name`)

### 3. Задачи (`/api/tasks/`)
| Метод | URL | Описание | Статус-код |
|-------|-----|----------|------------|
| `GET` | `/api/tasks/` | Список задач (пагинация, фильтрация, сортировка) | 200 OK |
| `POST` | `/api/tasks/` | Создание новой задачи | 201 Created |
| `GET` | `/api/tasks/{id}/` | Детальная информация о задаче с вложенными `project` и `assignee` | 200 OK |
| `PUT` | `/api/tasks/{id}/` | Полное обновление задачи | 200 OK |
| `PATCH` | `/api/tasks/{id}/` | Частичное обновление задачи | 200 OK |
| `DELETE` | `/api/tasks/{id}/` | Удаление задачи | 204 No Content |

**Query-параметры для `/api/tasks/`:**
* `?page=1&page_size=10` — пагинация (`PageNumberPagination`)
* `?status=todo` — фильтрация по статусу (`todo`, `in_progress`, `done`)
* `?priority=high` — фильтрация по приоритету (`low`, `medium`, `high`)
* `?project_id=1` (или `?project=1`) — фильтрация по проекту
* `?assignee_id=2` (или `?assignee=2`) — фильтрация по исполнителю
* `?ordering=-created_at` — сортировка (`created_at`, `due_date`, `priority`, `title`)

---

## Оптимизация запросов (Устранение проблемы N+1)

В слоях репозиториев (`repositories.py`) и сервисов (`services.py`) реализована предварительная загрузка связанных данных:
* Для сущности `Task`: используется `select_related("project", "project__owner", "assignee")`. Вся выборка списка задач со всеми связями выполняется за **1 SQL-запрос** (вместо $1 + 3N$).
* Для сущности `Project`: используется `select_related("owner")` и `prefetch_related("tasks__assignee", "tasks")`. Выборка проектов со всеми вложенными задачами и пользователями выполняется за **2 SQL-запроса** (вместо $1 + N + M$).
* Оптимизация валидирована интеграционными тестами с `assertNumQueries`.

---

## Формат ошибок (RFC 7807 Problem Details)

Все ошибки API стандартизированы кастомным обработчиком `custom_exception_handler` (`apps.tasks.exceptions.custom_exception_handler`) в единый формат RFC 7807:

```json
{
  "type": "urn:problem-type:unprocessable-entity",
  "title": "Unprocessable Entity",
  "status": 422,
  "detail": "Validation error: due_date: Due date cannot be in the past.",
  "instance": "/api/tasks/",
  "invalid_params": {
    "due_date": [
      "Due date cannot be in the past."
    ]
  }
}
```

Поддерживаемые статус-коды:
* `200 OK` — успешный запрос (GET, PUT, PATCH)
* `201 Created` — успешное создание ресурса (POST)
* `204 No Content` — успешное удаление ресурса (DELETE)
* `400 Bad Request` — синтаксические ошибки или некорректный формат запроса
* `404 Not Found` — запрашиваемый ресурс не найден
* `422 Unprocessable Entity` — семантические ошибки валидации полей и бизнес-правил

---

## Линтинг и форматирование кода

Для поддержания чистоты кода настроены конфигурации в `pyproject.toml` и `.flake8`.

Проверка линтером:
```bash
ruff check .
```

Автоматическое форматирование:
```bash
ruff format .
```