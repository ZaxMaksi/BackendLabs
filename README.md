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

### Реалізовані сутності:
1. **`User`** (`apps.tasks.models.User`): Кастомна модель на основі `AbstractUser` з рольовою моделлю (`admin`, `project_manager`, `member`).
2. **`Project`** (`apps.tasks.models.Project`): Проєкти з полями `name`, `description`, `created_at` та зв'язком `owner` (ForeignKey до `User`).
3. **`Task`** (`apps.tasks.models.Task`): Завдання з полями `title`, `description`, `status` (`todo`, `in_progress`, `done`), `priority` (`low`, `medium`, `high`), зв'язками з проєктом (`project`) та виконавцем (`assignee`), дедлайном `due_date` і датою створення `created_at`.
4. **`Attachment`** (`apps.tasks.models.Attachment`): Вкладення файлів до завдань з полями `file`, `task`, `uploaded_at`, `file_size` (у байтах), `content_type` (MIME-тип).

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

### 6. Запуск тестів (Pytest та Django Test Runner)
```bash
# Запуск через pytest:
pytest

# Або запуск через стандартний test runner Django:
python manage.py test apps.tasks
```

### 7. Запуск сервера розробки
```bash
python manage.py runserver
```

---

## Документація OpenAPI v3 та інтерактивний UI (Етап 3)

Проєкт підтримує автоматичну генерацію OpenAPI v3 специфікації за допомогою `drf-spectacular`. Усі ключові ендпоінти забезпечені детальними описами, параметрами фільтрації/пагінації та прикладами відповідей через `@extend_schema` і `@extend_schema_view`.

| URL | Формат | Опис |
|-----|--------|------|
| `/api/schema/swagger-ui/` | HTML | Інтерактивна документація **Swagger UI** |
| `/api/schema/redoc/` | HTML | Інтерактивна документація **ReDoc** |
| `/api/schema/` | YAML / JSON (`?format=json`) | Сира специфікація OpenAPI v3 |

---

## Ендпоінти API

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
| `GET` | `/api/tasks/{id}/attachments/` | Список усіх файлів-вкладень цього завдання | 200 OK |
| `POST` | `/api/tasks/{id}/attachments/` | Завантаження вкладення безпосередньо до цього завдання (`multipart/form-data`) | 201 Created |

**Query-параметри для `/api/tasks/`:**
* `?page=1&page_size=10` — пагінація (`PageNumberPagination`)
* `?status=todo` — фільтрація за статусом (`todo`, `in_progress`, `done`)
* `?priority=high` — фільтрація за пріоритетом (`low`, `medium`, `high`)
* `?project_id=1` (або `?project=1`) — фільтрація за проєктом
* `?assignee_id=2` (або `?assignee=2`) — фільтрація за виконавцем
* `?ordering=-created_at` — сортування (`created_at`, `due_date`, `priority`, `title`)

### 4. Файли-вкладення (`/api/attachments/`)
| Метод | URL | Опис | Статус-код |
|-------|-----|------|------------|
| `GET` | `/api/attachments/` | Список усіх вкладень (опціональний фільтр `?task_id=`) | 200 OK |
| `POST` | `/api/attachments/` | Завантаження файлу (`multipart/form-data` з полями `file` та `task_id` або `task`) | 201 Created |
| `GET` | `/api/attachments/{id}/` | Метадані файлу (ID, посилання, розмір, MIME, дата) | 200 OK |
| `DELETE` | `/api/attachments/{id}/` | Видалення вкладення та фізичного файлу зі сховища | 204 No Content |
| `GET` | `/api/attachments/{id}/download/` | Скачування файлу з заголовками `Content-Disposition: attachment` та `Content-Type` | 200 OK |

#### Валідація завантажуваних файлів:
1. **Обмеження за розміром:** Максимум 10 МБ (`MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024`). Порожні файли (0 байтів) також відхиляються.
2. **Дозволені розширення:** `pdf`, `png`, `jpg`, `jpeg`, `docx`, `txt`.
3. **Дозволені MIME-типи:** `application/pdf`, `image/png`, `image/jpeg`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/plain`.
4. У разі порушення обмежень повертається стандартна помилка RFC 7807 (`422 Unprocessable Entity`).

---

## Інтеграційне тестування (Етап 3)

У проєкті реалізовано 44 інтеграційних тести, що запускаються на ізольованій тестовій базі даних PostgreSQL:
* **Тестування повного циклу (ланцюжок: Запит → Відповідь → Стан БД):**
  * Створення ресурсу (`POST`) → перевірка HTTP 201 → пряма перевірка наявності та атрибутів у PostgreSQL через ORM.
  * Оновлення ресурсу (`PUT`/`PATCH`) → перевірка HTTP 200 → перевірка оновлених значень у PostgreSQL (`refresh_from_db`).
  * Видалення ресурсу (`DELETE`) → перевірка HTTP 204 → перевірка відсутності запису в PostgreSQL.
  * Каскадне видалення: Видалення проєкту видаляє всі пов'язані завдання та файли-вкладення.
* **Тестування завантаження та валідації файлів:**
  * Завантаження валідних PDF/PNG/TXT файлів (перевірка `file_size`, `content_type`, збереження на диску).
  * Скачування файлу (перевірка бінарного вмісту та заголовків).
  * Файл більший за 10 МБ → відхилення з кодом 422 (RFC 7807), стан БД залишається незмінним.
  * Файл з недозволеним розширенням (`.exe`, `.sh`) або MIME-типом → відхилення з кодом 422 (RFC 7807).
  * Порожній файл (0 байт) → відхилення з кодом 422.
* **Тестування документації OpenAPI:**
  * Доступність схем `/api/schema/` (YAML та JSON).
  * Доступність Swagger UI за адресою `/api/schema/swagger-ui/`.
  * Доступність ReDoc за адресою `/api/schema/redoc/`.

Запуск:
```bash
pytest
# або
python manage.py test apps.tasks
```

---

## Оптимізація запитів (Усунення проблеми N+1)

У шарах репозиторіїв (`repositories.py`) та сервісів (`services.py`) реалізовано оптимізацію запитів:
* Для сутності `Task`: використовується `select_related("project", "project__owner", "assignee")`. Вся вибірка списку завдань з усіма зв'язками виконується за **1 SQL-запит** (замість $1 + 3N$).
* Для сутності `Project`: використовується `select_related("owner")` та `prefetch_related("tasks__assignee", "tasks")`. Вибірка проєктів з усіма вкладеними завданнями та користувачами виконується за **2 SQL-запити** (замість $1 + N + M$).
* Оптимізація валідована тестами з `assertNumQueries`.

---

## Формат помилок (RFC 7807 Problem Details)

Усі помилки API стандартизовані кастомним обробником `custom_exception_handler` (`apps.tasks.exceptions.custom_exception_handler`) в єдиний формат RFC 7807:

```json
{
  "type": "urn:problem-type:unprocessable-entity",
  "title": "Unprocessable Entity",
  "status": 422,
  "detail": "File size exceeds limit of 10 MB (current size: 10486784 bytes).",
  "instance": "/api/attachments/",
  "invalid_params": {
    "file": [
      "File size exceeds limit of 10 MB (current size: 10486784 bytes)."
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
* `405 Method Not Allowed` — HTTP-метод не дозволено для цього ендпоінта
* `422 Unprocessable Entity` — семантичні помилки валідації полів, бізнес-правил та файлів
* `500 Internal Server Error` — внутрішня помилка сервера
* `503 Service Unavailable` — недоступність бази даних або сторонніх служб

---

## Лінтинг та форматування коду

Перевірка лінтером:
```bash
ruff check .
```

Автоматичне форматування:
```bash
ruff format .
```
