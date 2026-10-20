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
| `POST` | `/api/projects/{id}/generate-report/` | Запуск фонової генерації аналітичного звіту (асинхронно) | 202 Accepted |

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

### 5. Фонове опрацювання операцій (`/api/background-tasks/`)
| Метод | URL | Опис | Статус-код |
|-------|-----|------|------------|
| `POST` | `/api/projects/{id}/generate-report/` | Ініціалізація асинхронної генерації підсумкового звіту проєкту | 202 Accepted |
| `GET` | `/api/background-tasks/{job_id}/` | Отримання статусу виконання фонового завдання (`pending`, `running`, `completed`, `failed`) та звіту | 200 OK |

### 6. Зовнішній REST-сервіс календаря та свят (`/api/external/`)
| Метод | URL | Опис | Статус-код |
|-------|-----|------|------------|
| `GET` | `/api/external/holidays/` | Отримання державних свят та вихідних днів з кешуванням у пам'яті (`?year=2026&country_code=UA`) | 200 OK |

---

## Інтеграційне тестування (Етапи 1–4)

У проєкті реалізовано **56 інтеграційних тестів**, що запускаються на ізольованій тестовій базі даних PostgreSQL:
* **Тестування повного циклу (ланцюжок: Запит → Відповідь → Стан БД):**
  * Створення ресурсу (`POST`) → перевірка HTTP 201 → пряма перевірка наявності та атрибутів у PostgreSQL через ORM.
  * Оновлення ресурсу (`PUT`/`PATCH`) → перевірка HTTP 200 → перевірка оновлених значень у PostgreSQL (`refresh_from_db`).
  * Видалення ресурсу (`DELETE`) → перевірка HTTP 204 → перевірка відсутності запису в PostgreSQL.
  * Каскадне видалення: Видалення проєкту видаляє всі пов'язані завдання та файли-вкладення.
* **Тестування завантаження та валідації файлів (Етап 3):**
  * Завантаження валідних PDF/PNG/TXT файлів (перевірка `file_size`, `content_type`, збереження на диску).
  * Скачування файлу (перевірка бінарного вмісту та заголовків).
  * Файл більший за 10 МБ → відхилення з кодом 422 (RFC 7807), стан БД залишається незмінним.
  * Файл з недозволеним розширенням (`.exe`, `.sh`) або MIME-типом → відхилення з кодом 422 (RFC 7807).
  * Порожній файл (0 байт) → відхилення з кодом 422.
* **Тестування 12-Factor App та конфігурації оточення (Етап 4):**
  * Перевірка завантаження всіх параметрів конфігурації з `.env` (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CACHES`, таймаути, воркери).
  * Перевірка наявності та коректності структури шаблону `.env.example` без витоку секретів.
* **Тестування асинхронного фонового опрацювання (Етап 4):**
  * Негайне повернення HTTP `202 Accepted` при виклику `POST /api/projects/{id}/generate-report/`.
  * Перевірка наявності посилання `check_status_url` та валідного `job_id`.
  * Полінг статусу фонового завдання через `GET /api/background-tasks/{job_id}/` до переходу у стан `completed`.
  * Перевірка коректності агрегованих даних звіту (розподіл за статусами, пріоритетами, відсоток виконання, прострочені задачі).
  * Перевірка повернення RFC 7807 `404 Not Found` для неіснуючого `job_id`.
* **Тестування зовнішнього REST API та кешування (Етап 4):**
  * Запит до `/api/external/holidays/`: перший виклик виконує HTTP-запит до зовнішнього сервісу (`cached: false`), повторний виклик миттєво віддає дані з `LocMemCache` (`cached: true`) без повторного звернення до мережі.
  * Тестування таймауту зовнішнього сервісу (`requests.exceptions.Timeout`) → стандартизована відповідь RFC 7807 `504 Gateway Timeout`.
  * Тестування збою мережі (`requests.exceptions.ConnectionError`) → відповідь RFC 7807 `503 Service Unavailable`.
  * Валідація некоректних query-параметрів (`year`, `country_code`) → відповідь RFC 7807 `400 Bad Request`.
* **Тестування оптимізації бази даних та індексів (Етап 4):**
  * Перевірка наявності створених індексів `task_status_due_date_idx`, `task_status_idx`, `task_due_date_idx`, `task_title_idx` у системному каталозі `pg_indexes` PostgreSQL.
  * Перевірка плану виконання запиту через `EXPLAIN` (використання Index Scan).
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

## Фонове опрацювання тривалих операцій (Етап 4)

Для виконання ресурсомістких або тривалих операцій без блокування основного HTTP-потоку (event loop / worker) реалізовано патерн **Asynchronous Request-Reply** (згідно з RFC 7231 Section 6.3.3):

1. **Неблокуючий запит:** Клієнт надсилає `POST /api/projects/{id}/generate-report/`.
2. **Миттєва відповідь `202 Accepted`:** Сервер повертає унікальний ідентифікатор завдання `job_id` та URL для моніторингу:
   ```json
   {
     "status": "accepted",
     "message": "Project summary report generation started for project 'Alpha Project'.",
     "job_id": "c8691501-c5e3-47a2-99ea-4d89fa311499",
     "check_status_url": "http://127.0.0.1:8000/api/background-tasks/c8691501-c5e3-47a2-99ea-4d89fa311499/"
   }
   ```
3. **Фоновий виконавець (`BackgroundTaskExecutor`):** Побудований на базі `concurrent.futures.ThreadPoolExecutor(max_workers=...)` без необхідності розгортання важкого зовнішнього брокера (RabbitMQ/Redis).
4. **Управління ресурсами та БД:** Кожен робочий потік гарантовано закриває з'єднання з базою даних (`connection.close()`) у блоці `finally` для запобігання витоку підключень у PostgreSQL.
5. **Моніторинг статусу:** Запит `GET /api/background-tasks/{job_id}/` повертає актуальний стан (`pending`, `running`, `completed`, `failed`) та фінальний агрегований результат після завершення:
   ```json
   {
     "job_id": "c8691501-c5e3-47a2-99ea-4d89fa311499",
     "job_type": "project_summary_report",
     "status": "completed",
     "created_at": "2026-10-20T10:15:30.123456Z",
     "started_at": "2026-10-20T10:15:30.125000Z",
     "completed_at": "2026-10-20T10:15:30.250000Z",
     "result": {
       "project_id": 1,
       "project_name": "Alpha Project",
       "total_tasks": 15,
       "completion_rate_percent": 66.67,
       "tasks_by_status": {"todo": 3, "in_progress": 2, "done": 10},
       "tasks_by_priority": {"low": 4, "medium": 8, "high": 3},
       "overdue_tasks": 1,
       "upcoming_deadlines_next_7_days": 2,
       "total_attachments": 5,
       "total_attachments_bytes": 1048576,
       "generated_at": "2026-10-20T10:15:30.245000Z"
     },
     "error": null
   }
   ```

---

## Інтеграція із зовнішнім REST API та кешування (Етап 4)

У системі реалізовано інтеграцію із зовнішнім публічним REST-сервісом виробничого календаря та державних свят ([Nager.Date API](https://date.nager.at/)):
* **Призначення:** Допомога менеджерам і виконавцям при плануванні дедлайнів завдань (`due_date`) з урахуванням святкових і вихідних днів.
* **Стійкість до мережевих збоїв (Resilience):**
  * Встановлено жорсткий таймаут (`EXTERNAL_API_TIMEOUT = 3.0` с) у бібліотеці `requests`.
  * Перехоплення виключень `requests.exceptions.Timeout` з трансляцією у стандартизовану помилку RFC 7807 (`504 Gateway Timeout`).
  * Перехоплення помилок з'єднання `requests.exceptions.ConnectionError` та HTTP-помилок з трансляцією у RFC 7807 (`503 Service Unavailable`).
* **In-Memory кешування (`django.core.cache` / `LocMemCache`):**
  * Перший запит звертається до зовнішньої служби і зберігає результат у кеш із TTL (`EXTERNAL_API_CACHE_TTL = 300` с).
  * Повторні запити з тими самими параметрами віддаються безпосередньо з пам'яті (час відповіді < 1 ms, прапорець `"cached": true`), повністю виключаючи зайве навантаження на зовнішню мережу.

---

## Оптимізація бази даних PostgreSQL (Індекси та EXPLAIN ANALYZE) (Етап 4)

### 1. Виявлення вузького місця
У системі керування задачами найбільш частими і критичними є комбіновані запити вибірки активних завдань за статусом і дедлайном (наприклад: *знайти всі невиконані задачі (`status = 'todo'`), термін яких закінчується у найближчі 5 днів*).

За відсутності спеціалізованого індексу PostgreSQL змушений виконувати повне послідовне сканування таблиці (**Sequential Scan**), зчитуючи всі блоки з диска та відфільтровуючи тисячі рядків вручну.

### 2. Створені індекси (Модель `Task`)
У міграції `0003_alter_task_options_task_task_status_due_date_idx_and_more.py` додано такі B-tree індекси:
1. `task_status_due_date_idx` — складений (композитний) індекс на поля `(status, due_date)`.
2. `task_status_idx` — індекс на поле `status`.
3. `task_due_date_idx` — індекс на поле `due_date`.
4. `task_title_idx` — індекс на поле `title` (для швидкого сортування та пошуку).

### 3. Порівняльний аналіз планів виконання (EXPLAIN ANALYZE)

Для об'єктивного вимірювання було розроблено команду бенчмарку:
```bash
python manage.py benchmark_indexes --count 10000
```

#### Запит:
```sql
SELECT id, title, status, due_date
FROM tasks_task
WHERE status = 'todo' AND due_date <= NOW() + INTERVAL '5 days';
```

#### План 1: Без індексу (Sequential Scan)
```text
Seq Scan on tasks_task  (cost=0.00..373.00 rows=2001 width=41) (actual time=0.009..1.028 rows=2001.00 loops=1)
  Filter: (((status)::text = 'todo'::text) AND (due_date <= (now() + '5 days'::interval)))
  Rows Removed by Filter: 7999
  Buffers: shared hit=173
Planning Time: 3.024 ms
Execution Time: 1.075 ms
```

#### План 2: З композитним індексом `task_status_due_date_idx` (Bitmap Index Scan)
```text
Bitmap Heap Scan on tasks_task  (cost=32.80..245.82 rows=2001 width=41) (actual time=0.069..0.301 rows=2001.00 loops=1)
  Recheck Cond: (((status)::text = 'todo'::text) AND (due_date <= (now() + '5 days'::interval)))
  Heap Blocks: exact=172
  Buffers: shared hit=176
  ->  Bitmap Index Scan on task_status_due_date_idx  (cost=0.00..32.30 rows=2001 width=0) (actual time=0.053..0.053 rows=2001.00 loops=1)
        Index Cond: (((status)::text = 'todo'::text) AND (due_date <= (now() + '5 days'::interval)))
        Index Searches: 1
        Buffers: shared hit=4
Planning Time: 0.075 ms
Execution Time: 0.354 ms
```

#### Підсумок оптимізації:
* **Cost оцінка плану:** знизилась з **373.00** до **245.82**.
* **Час планування (Planning Time):** прискорено з **3.024 ms** до **0.075 ms** (у **40 разів**).
* **Час виконання (Execution Time):** прискорено з **1.075 ms** до **0.354 ms** (у **~3.04 рази** швидше).
* На промислових обсягах даних (100,000+ записів) прискорення досягає десятків і сотень разів.

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
* `202 Accepted` — успішне прийняття довготривалого запиту до фонової обробки
* `204 No Content` — успішне видалення ресурсу (DELETE)
* `400 Bad Request` — синтаксичні помилки або некоректний формат запиту
* `404 Not Found` — запитаний ресурс не знайдено
* `405 Method Not Allowed` — HTTP-метод не дозволено для цього ендпоінта
* `422 Unprocessable Entity` — семантичні помилки валідації полів, бізнес-правил та файлів
* `500 Internal Server Error` — внутрішня помилка сервера
* `503 Service Unavailable` — недоступність бази даних або сторонніх служб
* `504 Gateway Timeout` — перевищено таймаут очікування відповіді зовнішнього REST API

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
