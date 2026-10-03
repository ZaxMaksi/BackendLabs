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

## Эндпоинты Этапа 1

| Метод | URL | Описание | Ожидаемый ответ |
|-------|-----|----------|-----------------|
| `GET` | `/health` или `/health/` | Health-check сервиса и БД | `{"status": "ok"}` (200 OK) |
| `GET` | `/api/health/` | API-версия Health-check | `{"status": "ok"}` (200 OK) |
| `GET` | `/admin/` | Панель администратора Django | Страница авторизации Django Admin |

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