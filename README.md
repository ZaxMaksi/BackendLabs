# Task Tracker API (Система управління завданнями)

Лабораторний проєкт за темою 3.2 «Система управління завданнями (Трекер завдань)» на стеку **Python 3.10+ / Django / Django REST Framework / PostgreSQL**.

## Архітектура проєкту

Проєкт побудований за принципами багатошарової архітектури (Clean Architecture / Layered Monolith) з чітким розділенням відповідальності:

```text
HTTP Request
     │
     ▼
[ Views / Controllers ]  (src/apps/tasks/views.py)
     │
     ▼
[ Service Layer ]        (src/apps/tasks/services.py)  ── Бізнес-логіка та валідації
     │
     ▼
[ Repository Layer ]     (src/apps/tasks/repositories.py) ── Ізоляція direct ORM-запитів
     │
     ▼
[ Models / Django ORM ]  (src/apps/tasks/models.py)
     │
     ▼
[ PostgreSQL DB ]
```

### Реалізовані сутності (Етап 1):
1. **`User`** (`apps.tasks.models.User`): Кастомна модель на основі `AbstractUser` з рольовою моделлю (`admin`, `project_manager`, `member`).
2. **`Project`** (`apps.tasks.models.Project`): Проєкти з полями `name`, `description`, `created_at` та прив'язкою до власника `owner`.
3. **`Task`** (`apps.tasks.models.Task`): Завдання з полями `title`, `description`, `status` (`todo`, `in_progress`, `done`), `priority` (`low`, `medium`, `high`), зв'язками з проєктом (`project`) та виконавцем (`assignee`), дедлайном `due_date` і датою створення `created_at`.

---

## Вимоги

* Python 3.10+
* PostgreSQL 14+
* Віртуальне оточення (`venv`)

---

## Встановлення та запуск

### 1. Клонування репозиторію та перехід у проєкт
```bash
git clone <url_репозиторію>
cd task_tracker_project
```

### 2. Створення та активація віртуального оточення
```bash
python -m venv .venv

# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# Linux / macOS:
source .venv/bin/activate
```

### 3. Встановлення залежностей
```bash
pip install -r requirements.txt
```

### 4. Налаштування змінних оточення
Створіть файл `.env` у корені проєкту (за шаблоном):
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

### 5. Застосування міграцій до PostgreSQL
```bash
python manage.py migrate
```

### 6. Запуск тестів
```bash
python manage.py test apps.tasks
```

### 7. Запуск сервера розробки
```bash
python manage.py runserver
```

---

## Ендпоінти API (Етапи 1 і 2)

### 1. Сервісні ендпоінти
| Метод | URL | Опис | Очікувана відповідь |
|-------|-----|------|---------------------|
| `GET` | `/health` або `/health/` | Health-check сервісу та БД | `{"status": "ok"}` (200 OK) |
| `GET` | `/api/health/` | API-версія Health-check | `{"status": "ok"}` (200 OK) |
| `GET` | `/admin/` | Панель адміністратора Django | Django Admin |

### 2. Проєкти (`/api/projects/`)
| Метод | URL | Опис | Статус-код |
|-------|-----|------|------------|
| `GET` | `/api/projects/` | Список проєктів (пагінація, сортування, фільтрація) | 200 OK |
| `POST` | `/api/projects/` | Створення нового проєкту | 201 Created |
| `GET` | `/api/projects/{id}/` | Детальна інформація про проєкт із вкладеними завданнями та власником | 200 OK |
| `PUT` | `/api/projects/{id}/` | Повне оновлення проєкту | 200 OK |
| `PATCH` | `/api/projects/{id}/` | Часткове оновлення проєкту | 200 OK |
| `DELETE` | `/api/projects/{id}/` | Видалення проєкту | 204 No Content |

**Query-параметри для `/api/projects/`:**
* `?page=1&page_size=10` — пагінація (`PageNumberPagination`)
* `?owner_id=1` (або `?owner=1`) — фільтрація за власником проєкту
* `?name=Alpha` — пошук/фільтрація за назвою
* `?ordering=-created_at` — сортування (`created_at`, `-created_at`, `name`, `-name`)

### 3. Завдання (`/api/tasks/`)
| Метод | URL | Опис | Статус-код |
|-------|-----|------|------------|
| `GET` | `/api/tasks/` | Список завдань (пагінація, фільтрація, сортування) | 200 OK |
| `POST` | `/api/tasks/` | Створення нового завдання | 201 Created |
| `GET` | `/api/tasks/{id}/` | Детальна інформація про завдання із вкладеними `project` та `assignee` | 200 OK |
| `PUT` | `/api/tasks/{id}/` | Повне оновлення завдання | 200 OK |
| `PATCH` | `/api/tasks/{id}/` | Часткове оновлення завдання | 200 OK |
| `DELETE` | `/api/tasks/{id}/` | Видалення завдання | 204 No Content |

**Query-параметри для `/api/tasks/`:**
* `?page=1&page_size=10` — пагінація (`PageNumberPagination`)
* `?status=todo` — фільтрація за статусом (`todo`, `in_progress`, `done`)
* `?priority=high` — фільтрація за пріоритетом (`low`, `medium`, `high`)
* `?project_id=1` (або `?project=1`) — фільтрація за проєктом
* `?assignee_id=2` (або `?assignee=2`) — фільтрація за виконавцем
* `?ordering=-created_at` — сортування (`created_at`, `due_date`, `priority`, `title`)

---

## Оптимізація запитів (Усунення проблеми N+1)

У шарах репозиторіїв (`repositories.py`) та сервісів (`services.py`) реалізовано попереднє завантаження пов'язаних даних:
* Для сутності `Task`: використовується `select_related("project", "project__owner", "assignee")`. Вся вибірка списку завдань з усіма зв'язками виконується за **1 SQL-запит** (замість $1 + 3N$).
* Для сутності `Project`: використовується `select_related("owner")` та `prefetch_related("tasks__assignee", "tasks")`. Вибірка проєктів з усіма вкладеними завданнями та користувачами виконується за **2 SQL-запити** (замість $1 + N + M$).
* Оптимізація валідована інтеграційними тестами з `assertNumQueries`.

---

## Формат помилок (RFC 7807 Problem Details)

Усі помилки API стандартизовані кастомним обробником `custom_exception_handler` (`apps.tasks.exceptions.custom_exception_handler`) в єдиний формат RFC 7807:

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

Підтримувані статус-коди:
* `200 OK` — успішний запит (GET, PUT, PATCH)
* `201 Created` — успішне створення ресурсу (POST)
* `204 No Content` — успішне видалення ресурсу (DELETE)
* `400 Bad Request` — синтаксичні помилки або некоректний формат запиту
* `404 Not Found` — запитаний ресурс не знайдено
* `422 Unprocessable Entity` — семантичні помилки валідації полів та бізнес-правил

---

## Лінтинг та форматування коду

Для підтримки чистоти коду налаштовано конфігурації у `pyproject.toml` та `.flake8`.

Перевірка лінтером:
```bash
ruff check .
```

Автоматичне форматування:
```bash
ruff format .
```