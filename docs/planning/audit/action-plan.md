# Комплексный инженерный план действий (Production-Grade Engineering Action Plan: rost_crm)

**Дата составления:** 22 сентября 2026 года  
**Базовый коммит (Git Baseline):** `1c7c0eb35caaababb8708f1d5f109866ac7b420a` (`1c7c0eb`)  
**Объект планирования:** Кодовая база `rost_crm` (FastAPI, React SPA, PostgreSQL, Keycloak OIDC, Nginx, Docker Compose), эталонная архитектура (`docs/architecture/01-06`, `c4-architecture.md`), правила разработки (`AGENTS.md`), мастер-анализ разрывов (`07-gap-analysis.md`) и результаты 8 доменных аудитов (`domain-01` — `domain-08`).  
**Статус документа:** Официальный производственный инженерный план реализации (Production Engineering Action Plan).  
**Распределение ролей:** Разработчик A (Backend Core, Infra, DB, Security) и Разработчик B (Frontend, Reports, Imports, E2E, Help).

---

## 1. Executive Summary & Философия реализации (The Ponytail Ladder)

### 1.1. Контекст и цели документа
Настоящий инженерный план регламентирует устранение архитектурных разрывов и поэтапное развитие системы «ИТ Школа Ростелекома — CRM» (`rost_crm`). План структурирован по трем горизонтам зрелости:
1. **Horizon Gate D (Хакатон / Демо-показ — Задачи P0):** Срочный пакет из 6 точечных инженерных исправлений, устраняющих критические дефекты многопоточности, безопасности контейнеров, целостности внешних ключей и синхронизации UI/API перед итоговой защитой проекта. Трудозатраты: ~2.8 часа инженерного времени.
2. **Horizon Gate P (Опытно-промышленный пилот — Задачи P1):** Внедрение версионированных миграций Alembic с выделенным контейнером `db-migrator`, подключение боевых сетевых Live HTTP-клиентов для LMS Zion и Laravel CMS Website, трехуровневая сетевая сегментация Docker, включение Gzip-сжатия и сквозного трейсинга `X-Request-ID`, а также нормализация контактной модели вузов.
3. **Horizon Gate O (Промышленная эксплуатация / Масштабирование — Задачи P2):** Переход на распределенную очередь фоновых задач (Redis Broker, Celery/RQ Workers, Transactional Outbox), внедрение глобального счетчика эпохи политик доступа `access_policy_state.epoch` (`authz_epoch`), материализация темпоральных фактов (`state_visit`, `report_run`, `report_row`) и интеграция с потоковым сокетом ClamAV (`clamd`).

---

### 1.2. Методология Ponytail: Принцип «Лестницы» (The Ladder, Ступени 1–7)
В соответствии с требованиями `AGENTS.md` и регламентом проекта, каждый пункт плана и любое последующее изменение кода обязаны следовать строгой дисциплине «Лестницы» (The Ladder):

```
                        ЛЕСТНИЦА PONYTAIL (THE LADDER)
  ┌────────────────────────────────────────────────────────────────────────┐
  │ Ступень 1: YAGNI ── Нужно ли создавать? Отбросить спекулятивное        │
  │ Ступень 2: REUSE ── Уже есть в коде? Переиспользовать существующее     │
  │ Ступень 3: STDLIB ─ Стандартная библиотека Python/JS делает это?       │
  │ Ступень 4: NATIVE ─ Нативная фича платформы закрывает вопрос? (CSS, DB)│
  │ Ступень 5: DEPS ─── Уже установленная зависимость решает задачу?       │
  │ Ступень 6: 1-LINER  Сделать в одну строку / минимальным diff           │
  │ Ступень 7: ROOT ─── Починить первопричину, а не ставить заплатки       │
  └────────────────────────────────────────────────────────────────────────┘
```

- **Ступень 1 (YAGNI — You Aren't Gonna Need It):** Отказ от избыточных 58 таблиц эталонной 77-табличной схемы на этапе Gate D; сохранение расчетных отчетов on-the-fly без материализации миллионов строк в `report_run`/`report_row` до наступления эмпирических порогов нагрузки.
- **Ступень 2 (Переиспользование):** Повторное использование встроенных хелперов `scoped_interaction`, `cas()`, `append_event()`, `begin_command()` и компонентов `ui.tsx`.
- **Ступень 3 (Стандартная библиотека):** Использование `stdlib` Python (`anyio`, `email.message_from_bytes`, `hashlib`, `zipfile`, `urllib.request`, `pathlib`) и JavaScript (`crypto.randomUUID()`) вместо раздувания `requirements.txt` и `package.json`.
- **Ступень 4 (Нативные возможности платформы):** Использование директив СУБД (`ON DELETE SET NULL`, `PRAGMA journal_mode=WAL`, `CHECK`), директив Nginx (`client_max_body_size`, `gzip`, `add_header`) и нативных HTML5/CSS возможностей вместо тяжелых сторонних фреймворков.
- **Ступень 5 (Имеющиеся зависимости):** Строгое сохранение состава `requirements.txt` (ровно 6 проверенных библиотек для Gate D) и `package.json` (3 runtime-библиотеки: React 19, ReactDOM, Keycloak-js).
- **Ступень 6 (Минимальный diff):** Побеждает наименьший рабочий diff, затрагивающий минимальное число строк и файлов.
- **Ступень 7 (Root Cause):** Устранение первопричины дефекта в единой точке входа, а не нагромождение локальных заплат.

---

### 1.3. Архитектурные инварианты (Non-Negotiable Invariants)
Любые модификации в рамках настоящего плана подчиняются безусловным ограничениям:
1. **152-ФЗ и ФСТЭК №117 (Изоляция данных):** Менеджер видит только свои карточки (`owner_id == user.id`), руководитель — только карточки своего подразделения (`team_id == user.team_id`), администратор имеет нулевой неявный коммерческий доступ. Попытка запроса чужого объекта возвращает строго **HTTP 404 Not Found** (сокрытие факта существования, anti-IDOR).
2. **In-Memory хранение токенов:** JWT-токены сессии удерживаются исключительно в оперативной памяти JavaScript через React `useRef`. Вызовы `localStorage.setItem` и `sessionStorage.setItem` строго запрещены.
3. **Zero-Oracle Architecture:** Проверка области доступа (`scoped_interaction`) выполняется строго ДО парсинга содержимого файла или тела запроса. Неавторизованный запрос возвращает 404, подавляя коды 413 и 422.
4. **Non-Root исполнение:** Все контейнеры исполняются под непривилегированными системными пользователями (`appuser:10001` в бэкенде, `nginx:101` во фронтенде).
5. **CAS-конкурентность:** Все мутирующие операции обязаны проверять ревизию через CAS-условие `WHERE id=:id AND revision=:expected_revision` и требовать заголовок `Idempotency-Key` (до 200 символов).

---

## 2. Horizon Gate D: Хакатон / Демо-показ (Задачи P0)

Сводная матрица задач Horizon Gate D:

| ID | Наименование задачи | Исполнитель | Трудозатраты | Затронутые файлы и строки | Предостережение (Advisory) |
|:---:|---|:---:|:---:|---|:---:|
| **TASK-D01** | AnyIO Limiter & QueuePool Synchronization | Dev A | 30 мин | `backend/app/main.py:117-120`<br>`backend/app/db.py:18-23` | Advisory 1: QueuePool Starvation |
| **TASK-D02** | Nginx CSP for Keycloak HTTPS | Dev A | 15 мин | `deploy/nginx.conf:30` | Mixed Content / OIDC Block |
| **TASK-D03** | Nginx 26m Body Size & CI Oracle Alignment | Dev A | 20 мин | `deploy/nginx.conf:26`<br>`docs/checks/verify_infra.py:68, 77` | Advisory 4: CI Oracle Desync |
| **TASK-D04** | Backend Dockerfile Non-Root Code Protection | Dev A | 15 мин | `backend/Dockerfile:12` | CIS Docker Benchmark |
| **TASK-D05** | Attachments Idempotency & CAS with UI Sync | Dev A + Dev B | 45 мин | `backend/app/main.py:289-308`<br>`backend/app/files.py:100-150`<br>`frontend/src/views/InteractionPage.tsx:297-300` | Advisory 2: UI FormData Breakdown |
| **TASK-D06** | Teams Table & Pre-Seeded Integrity | Dev A | 45 мин | `backend/app/models.py:24, 115`<br>`backend/app/seed.py:27-32, 43-45`<br>`backend/tests/*` | Advisory 3: Seed Integrity Breakdown |

---

### TASK-D01: AnyIO Limiter & QueuePool Synchronization
- **Исполнитель:** Разработчик A | **Оценка трудозатрат:** 30 минут
- **Зона файлов:** `backend/app/main.py:117-120`, `backend/app/db.py:18-23`
- **Суть дефекта:**
  В штатном коде `main.py` контекстный менеджер `lifespan` пуст (`yield`), из-за чего лимитер пула рабочих потоков AnyIO остается на дефолтном значении 40 токенов. В `backend/app/db.py` параметры пула соединений SQLAlchemy не заданы явно, что для PostgreSQL и файлового SQLite активирует дефолтный `QueuePool(pool_size=5, max_overflow=10)` — суммарно ровно **15 соединений**. При нагрузке 50 одновременных пользователей и 10 параллельных запросов отчетов возникает каскадный коллапс: AnyIO блокирует входящие потоки, а вызовы `get_db()` зависают в очереди ожидания соединений с падением по таймауту 30 секунд: `TimeoutError: QueuePool limit of size 5 overflow 10 reached`.
- **⚠️ Критическое предостережение ревьюера (Adversarial Advisory 1 — QueuePool Starvation):**
  Простое увеличение лимитера `anyio.to_thread.current_default_thread_limiter().total_tokens = 120` в `main.py` без пропорционального расширения `QueuePool` в `db.py` смещает точку отказа на уровень пула СУБД. При 60 одновременных потоках 15 сессий захватят соединения, а остальные 45 потоков будут принудительно заблокированы и выбросят исключение. Расширение лимитера AnyIO и пула соединений SQLAlchemy обязано производиться строго синхронно!
- **Проект изменений (Diff):**

*1. `backend/app/main.py` (строки 117–121):*
```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -117,4 +117,7 @@ def create_app(settings: Settings | None = None) -> FastAPI:
     @asynccontextmanager
     async def lifespan(app: FastAPI):
+        import anyio.to_thread
+        # Синхронизация лимитера AnyIO под нагрузочный профиль 50 пользователей + 10 отчетов
+        anyio.to_thread.current_default_thread_limiter().total_tokens = 120
         yield
```

*2. `backend/app/db.py` (строки 18–35):*
```diff
--- a/backend/app/db.py
+++ b/backend/app/db.py
@@ -18,12 +18,22 @@ def get_engine(url=None):
     options = {"pool_pre_ping": True}
     if url.startswith("sqlite"):
-        options["connect_args"] = {"check_same_thread": False, "timeout": 20}
+        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
         if ":memory:" in url:
             options["poolclass"] = StaticPool
+        else:
+            options["pool_size"] = 30
+            options["max_overflow"] = 90
+            options["pool_timeout"] = 30
+    else:
+        # PostgreSQL QueuePool: 30 pool_size + 90 max_overflow = 120 соединений
+        options["pool_size"] = 30
+        options["max_overflow"] = 90
+        options["pool_timeout"] = 30
     engine = create_engine(url, **options)
     if url.startswith("sqlite"):
         @event.listens_for(engine, "connect")
         def sqlite_options(connection, _):
             connection.execute("PRAGMA foreign_keys=ON")
-            connection.execute("PRAGMA busy_timeout=20000")
+            connection.execute("PRAGMA busy_timeout=30000")
+            connection.execute("PRAGMA journal_mode=WAL")
+            connection.execute("PRAGMA synchronous=NORMAL")
     return engine
```
- **Команды верификации:**
  ```bash
  # 1. Проверка синтаксиса и импортов
  python3 -c "from app.main import create_app; from app.db import get_engine; app = create_app(); print('App and Engine OK')"
  # 2. Прогон нагрузочного теста
  python3 backend/benchmarks/benchmark_load.py
  # 3. Регрессионный тест
  backend/.venv/bin/pytest backend/tests/test_working_slice.py
  ```

---

### TASK-D02: Nginx CSP for Keycloak HTTPS
- **Исполнитель:** Разработчик A | **Оценка трудозатрат:** 15 минут
- **Зона файлов:** `deploy/nginx.conf:30`
- **Суть дефекта:**
  В конфигурации Nginx заголовок Content-Security-Policy в директиве `connect-src` содержит только `'self' http: ws:;`. При развертывании в защищенном контуре с TLS (HTTPS) браузер пользователя блокирует вызовы фронтенда к внешнему серверу Keycloak (`https://auth.domain.rt.ru`) и защищенным веб-сокетам (`wss:`), генерируя ошибку Mixed Content / CSP Violation и блокируя вход в систему.
- **Проект изменений (Diff):**

```diff
--- a/deploy/nginx.conf
+++ b/deploy/nginx.conf
@@ -30,1 +30,1 @@
-        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http: ws:;" always;
+        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https: http: wss: ws:;" always;
```
- **Команды верификации:**
  ```bash
  # 1. Проверка директивы в файле
  grep -n "connect-src" deploy/nginx.conf
  # 2. Валидация через проверочный оракул
  python3 docs/checks/verify_infra.py
  ```

---

### TASK-D03: Nginx 26m Body Size & CI Oracle Atomic Alignment
- **Исполнитель:** Разработчик A | **Оценка трудозатрат:** 20 минут
- **Зона файлов:** `deploy/nginx.conf:26`, `docs/checks/verify_infra.py:68, 77`
- **Суть дефекта:**
  Лимит Nginx `client_max_body_size 25m;` равен ровно $26\,214\,400$ байт. При загрузке разрешенного ТЗ файла размером ровно 25.0 МБ накладные расходы протокола `multipart/form-data` (boundary-маркеры, заголовки `Content-Disposition`) увеличивают общий размер HTTP-запроса примерно на 300–400 байт (до $26\,214\,750$ байт). Nginx принудительно обрывает запрос с кодом 413 и HTML-страницей, не позволяя запросу дойти до FastAPI и нарушая контракт унифицированной JSON-ошибки `{error: {code: "FILE_TOO_LARGE"}}`.
- **⚠️ Критическое предостережение ревьюера (Adversarial Advisory 4 — CI Oracle Desynchronization):**
  Скрипт `docs/checks/verify_infra.py:68, 77` жестко проверяет строгое равенство: `nginx_bytes == 25 * 1024 * 1024` и `nginx_bytes == backend_bytes`. Изменение `nginx.conf` на `26m` без одновременного расширения проверочного оракула приведет к падению CI-пайплайна со статусом FAIL. Модификация `deploy/nginx.conf` и `docs/checks/verify_infra.py` обязана выполняться строго **атомарно в рамках одного коммита**!
- **Проект изменений (Diff):**

*1. `deploy/nginx.conf` (строка 26):*
```diff
--- a/deploy/nginx.conf
+++ b/deploy/nginx.conf
@@ -26,1 +26,1 @@
-        client_max_body_size 25m;
+        client_max_body_size 26m;
```

*2. `docs/checks/verify_infra.py` (строки 67–79):*
```diff
--- a/docs/checks/verify_infra.py
+++ b/docs/checks/verify_infra.py
@@ -67,3 +67,3 @@
     val, unit = int(size_match.group(1)), size_match.group(2).lower()
     nginx_bytes = val * (1024 * 1024 if unit == "m" else 1024 if unit == "k" else 1024**3 if unit == "g" else 1)
-    require(nginx_bytes == 25 * 1024 * 1024, f"nginx client_max_body_size must be 25m, got {val}{unit}")
+    require(nginx_bytes in (25 * 1024 * 1024, 26 * 1024 * 1024), f"nginx client_max_body_size must be 25m or 26m, got {val}{unit}")
@@ -76,3 +76,3 @@
     # Cross-consistency
-    require(nginx_bytes == backend_bytes,
-            f"Size mismatch: nginx={nginx_bytes} bytes vs backend={backend_bytes} bytes")
+    require(nginx_bytes >= backend_bytes,
+            f"Nginx body limit ({nginx_bytes}) must be >= backend MAX_FILE_SIZE ({backend_bytes})")
```
- **Команды верификации:**
  ```bash
  python3 docs/checks/verify_infra.py
  # Ожидаемый вывод: ALL INFRASTRUCTURE AND DEVSECOPS CHECKS PASSED.
  ```

---

### TASK-D04: Backend Dockerfile Non-Root Code Protection
- **Исполнитель:** Разработчик A | **Оценка трудозатрат:** 15 минут
- **Зона файлов:** `backend/Dockerfile:12`
- **Суть дефекта:**
  Инструкция `COPY --chown=appuser:appuser app ./app` передает права владения исходными файлами Python непривилегированному пользователю рантайма `appuser`. В случае уязвимости в приложении или зависимостях скомпрометированный процесс получает возможность модифицировать или перезаписывать собственные исходные коды на диске. По требованиям CIS Docker Benchmark исполняемые файлы должны принадлежать `root:root` (read-only для рантайма), а право записи предоставляется исключительно каталогу хранилища `/app/storage`.
- **Проект изменений (Diff):**

```diff
--- a/backend/Dockerfile
+++ b/backend/Dockerfile
@@ -12,1 +12,1 @@
-COPY --chown=appuser:appuser app ./app
+COPY app ./app
```
- **Команды верификации:**
  ```bash
  python3 docs/checks/verify_infra.py
  # Проверка прав в собранном образе (при наличии Docker):
  # docker build -t rtk-crm-backend:test ./backend
  # docker run --rm rtk-crm-backend:test ls -ld /app/app
  ```

---

### TASK-D05: Attachments Idempotency & CAS with UI Sync
- **Исполнитель:** Разработчик A (Backend) и Разработчик B (Frontend) | **Оценка трудозатрат:** 45 минут
- **Зона файлов:**
  - `backend/app/main.py:289-308`
  - `backend/app/files.py:100-150`
  - `frontend/src/views/InteractionPage.tsx:297-300`
- **Суть дефекта:**
  Эндпоинт загрузки файлов `POST /api/v1/interactions/{id}/attachments` не выполняет проверку `expected_revision` через `cas()` и не принимает заголовок `Idempotency-Key`. При параллельной загрузке двух файлов в одну карточку оба потока вычисляют одинаковый следующий `sequence` для журнала событий, вызывая коллизию уникального индекса `uq_event_sequence` и неконтролируемый сбой HTTP 500.
- **⚠️ Критическое предостережение ревьюера (Adversarial Advisory 2 — UI FormData Breakdown):**
  Во фронтенде `InteractionPage.tsx:297-300` объект `FormData` содержит только `file`. Если на бэкенде сделать аргумент `expected_revision: int = Form(...)` строго обязательным без синхронного обновления фронтенда, все операции прикрепления файлов в веб-интерфейсе немедленно завершатся с ошибкой **HTTP 422 Unprocessable Entity**. Требуется согласованное сквозное изменение:
  1. Frontend передает ревизию карточки: `formData.append('expected_revision', String(item.revision))`.
  2. Backend объявляет параметр опциональным: `expected_revision: int | None = Form(None)` с проверкой `cas()` только при наличии значения (плавный переход).
- **Проект изменений (Diff):**

*1. `frontend/src/views/InteractionPage.tsx` (строки 297–301):*
```diff
--- a/frontend/src/views/InteractionPage.tsx
+++ b/frontend/src/views/InteractionPage.tsx
@@ -297,2 +297,5 @@
       const formData = new FormData();
       formData.append('file', file);
+      if (item?.revision !== undefined) {
+        formData.append('expected_revision', String(item.revision));
+      }
       await api.upload('/interactions/' + encodeURIComponent(id) + '/attachments', formData, makeMutationKey());
```

*2. `backend/app/main.py` (строки 289–309):*
```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -289,6 +289,7 @@ def create_app(settings: Settings | None = None) -> FastAPI:
     @app.post("/api/v1/interactions/{interaction_id}/attachments", status_code=201, tags=["attachments"])
     async def upload_attachment(
         interaction_id: str,
         request: Request,
+        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
         db: Session = Depends(get_db),
         user: User = Depends(current_user),
     ):
@@ -296,5 +297,14 @@ def create_app(settings: Settings | None = None) -> FastAPI:
-        scoped_interaction(db, user, interaction_id)
-        filename, file_bytes, content_type = await _extract_uploaded_file(request)
+        item = scoped_interaction(db, user, interaction_id)
+        filename, file_bytes, content_type, exp_rev = await _extract_uploaded_file_and_revision(request)
+        if exp_rev is not None:
+            cas(db, item, exp_rev)
+        if idempotency_key:
+            cached = begin_command(db, user, "upload_attachment", idempotency_key, interaction_id)
+            if cached:
+                return cached
         att = save_attachment(
             db,
             user,
             interaction_id,
             filename,
             file_bytes,
             storage_dir=config.storage_dir,
             content_type_header=content_type,
         )
         result = attachment_dict(att)
+        if idempotency_key:
+            finish_command(db, user, "upload_attachment", idempotency_key, interaction_id, result)
         db.commit()
         return result
```
- **Команды верификации:**
  ```bash
  # 1. Прогон тестов файловой подсистемы
  backend/.venv/bin/pytest backend/tests/test_attachments.py
  # 2. Прогон тестов конкурентности и безопасности
  backend/.venv/bin/pytest backend/tests/test_core_concurrency_and_security.py -k "attachment"
  # 3. Проверка сборки фронтенда TypeScript
  (cd frontend && pnpm build)
  ```

---

### TASK-D06: Teams Table & Pre-Seeded Integrity
- **Исполнитель:** Разработчик A | **Оценка трудозатрат:** 45 минут
- **Зона файлов:**
  - `backend/app/models.py:24, 115`
  - `backend/app/seed.py:27-32, 43-45`
  - `backend/tests/`
- **Суть дефекта:**
  Поле `team_id` в таблицах `users` и `interactions` является обычной строкой `String(64)` без внешнего ключа `ForeignKey`. Таблица `teams` отсутствует. Это не позволяет гарантировать ссылочную целостность подразделений и реляционную изоляцию прав руководителей (`supervisor`).
- **⚠️ Критическое предостережение ревьюера (Adversarial Advisory 3 — Seed & Test Integrity Breakdown):**
  В `seed.py` и существующих автотестах пользователи и взаимодействия создаются с `team_id="north"`, `"south"`, `"team-alpha"` и `"team-beta"` ДО создания каких-либо записей команд. Простое добавление `ForeignKey("teams.id")` без предварительного создания записей команд (pre-seeding) вызовет немедленное падение инициализации базы и 100% автотестов с ошибкой `IntegrityError (foreign key constraint failed)`. Создание команд в `seed.py` и фикстурах тестов обязано строго предшествовать вставке пользователей и взаимодействий!
- **Проект изменений (Diff):**

*1. `backend/app/models.py`:*
```diff
--- a/backend/app/models.py
+++ b/backend/app/models.py
@@ -17,2 +17,9 @@ def utcnow() -> datetime:
     return datetime.now(timezone.utc)
 
+class Team(Base):
+    __tablename__ = "teams"
+    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
+    name: Mapped[str] = mapped_column(String(200), nullable=False)
+    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
+
@@ -24,1 +31,1 @@ class User(Base):
-    team_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
+    team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
@@ -115,1 +122,1 @@ class Interaction(Base):
-    team_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
+    team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.id", ondelete="SET NULL"), index=True, nullable=True)
```

*2. `backend/app/seed.py` (pre-seeding команд перед пользователями):*
```diff
--- a/backend/app/seed.py
+++ b/backend/app/seed.py
@@ -9,2 +9,3 @@ from .models import (
     Contract,
     Direction,
+    Team,
@@ -43,3 +44,13 @@ def seed_database(db: Session) -> None:
+    # Pre-seeding команд для удовлетворения Foreign Key ограничений
+    teams = {
+        "north": "Команда Север",
+        "south": "Команда Юг",
+        "team-alpha": "Команда Альфа",
+        "team-beta": "Команда Бета",
+    }
+    for ident, name in teams.items():
+        _get_or_add(db, Team, ident, name=name)
+    db.flush()
+
     directions = {
```
- **Команды верификации:**
  ```bash
  # 1. Проверка инициализации схемы и сидинга базы данных
  python3 -m app.seed --init-db
  # 2. Проверка полного тестового сьюта
  backend/.venv/bin/pytest backend/tests/
  # Ожидаемый результат: 184 passed
  ```

---

## 3. Horizon Gate P: Опытно-промышленный пилот (Задачи P1)

| ID | Наименование задачи | Исполнитель | Трудозатраты | Целевой контур |
|:---:|---|:---:|:---:|---|
| **TASK-P01** | Alembic Versioned Migrations & db-migrator | Dev A | 4–6 дн. | `backend/alembic/`, `compose.yaml` |
| **TASK-P02** | Live HTTP-Clients for Zion & Laravel CMS | Dev A | 4–6 дн. | `backend/app/integrations/live_*.py` |
| **TASK-P03** | Docker Compose Network Segmentation | Dev A | 2–3 дн. | `compose.yaml` |
| **TASK-P04** | Nginx Gzip Compression & X-Request-ID Tracing | Dev A + Dev B | 2–3 дн. | `deploy/nginx.conf`, `backend/app/main.py` |
| **TASK-P05** | University Contact Normalization & Junction Tables | Dev A + Dev B | 3–5 дн. | `backend/app/models.py`, `frontend/src/` |

---

### TASK-P01: Alembic Versioned Migrations & db-migrator container/Job
- **Цель:** Исключить рантайм-вызов `Base.metadata.create_all()`. Развернуть версионированные миграции на базе Alembic с единым линейным графом ревизий.
- **Инженерное решение:**
  1. Создать каталог `backend/alembic/` с шаблоном окружения `env.py`, настроенным на чтение `Base.metadata` из `app.models`.
  2. Сгенерировать базовую ревизию `0001_initial_schema.py`, воспроизводящую текущее состояние схемы базы данных коммита `1c7c0eb` + задачи Gate D.
  3. Ввести в `compose.yaml` выделенный сервис `db-migrator`:
     ```yaml
     db-migrator:
       build:
         context: ./backend
       environment:
         DATABASE_URL: postgresql+psycopg://rtk_crm_migrator:${MIGRATOR_DB_PASSWORD}@postgres:5432/rtk_crm
       command: ["alembic", "upgrade", "head"]
       depends_on:
         postgres:
           condition: service_healthy
     ```
  4. Настроить запуск сервиса `api` строго после успешного завершения мигратора: `condition: service_completed_successfully`.
  5. Разделить привилегии в PostgreSQL: пользователь `rtk_crm_migrator` обладает правами DDL (`CREATE`, `ALTER`, `DROP`), а пользователь приложения `rtk_crm` — строго правами DML (`SELECT`, `INSERT`, `UPDATE`, `DELETE`).
- **Откат (Rollback Procedure):** В каждой миграции обязательно реализуется функция `downgrade()`. Процедура отката тестируется в CI на чистой и наполненной базе.

---

### TASK-P02: Live HTTP-Clients for LMS Zion and Laravel CMS Website via httpx
- **Цель:** Заменить симуляторы `MockLMSAdapter` и `MockWebsiteAdapter` реальными сетевыми клиентами, соблюдая изоляцию и контракт C07.
- **Инженерное решение:**
  1. Реализовать `ZionLMSClient` и `LaravelWebsiteClient` на базе библиотеки `httpx` (или стандартного `urllib.request` в соответствии со ступенью 3 Ponytail).
  2. Поддержать аутентификацию по Bearer-токену и взаимному TLS (mTLS) при передаче ПДн.
  3. Реализовать устойчивость к сетевым сбоям: пул соединений (`keepalive`), экспоненциальный retry с джиттером (`tenacity` или рукописный хелпер), ограничение таймаута соединения (5 секунд) и чтения (30 секунд).
  4. Выполнять нормализацию получаемых данных в датакласс `NormalizedEnvelope` с обязательным вычислением хеша полезной нагрузки `payload_hash = hashlib.sha256(raw_bytes).hexdigest()`.
  5. При повторной доставке пакета проверять совпадение `payload_hash`: при несовпадении переводить запись в статус `reconciliation_case` с кодом `SOURCE_PAYLOAD_CONFLICT`.

---

### TASK-P03: Docker Compose Network Segmentation
- **Цель:** Ликвидировать единую плоскую сеть `rtk-crm_default`. Изолировать порт PostgreSQL от веб-контура Nginx.
- **Инженерное решение:**
  1. Выделить 4 сегмента сети в `compose.yaml`:
     - `frontend_net`: внешняя сеть между Nginx (`frontend`) и Uvicorn (`api`).
     - `backend_net`: внутренняя сеть между Uvicorn (`api`), PostgreSQL и Keycloak (`internal: true`).
     - `auth_net`: внутренняя сеть между Keycloak и PostgreSQL (`internal: true`).
     - `db_net`: изолированная внутренняя сеть СУБД (`internal: true`).
  2. Контейнер `frontend` подключается **только** к `frontend_net`. Прямой сетевой доступ из веб-сервера к порту 5432 СУБД физически исключается на уровне ядра Linux (iptables / bridge network).
  3. Контейнер `api` подключается к `frontend_net` и `backend_net`, выполняя функцию защищенного межсетевого шлюза.

---

### TASK-P04: Nginx Gzip Compression & X-Request-ID End-to-End Tracing
- **Цель:** Оптимизировать сетевой трафик для соблюдения секундного SLA (R18) и обеспечить сквозной аудит по требованиям ФСТЭК №117.
- **Инженерное решение:**
  1. В `deploy/nginx.conf` включить модуль динамического сжатия:
     ```nginx
     gzip on;
     gzip_vary on;
     gzip_proxied any;
     gzip_comp_level 6;
     gzip_min_length 1024;
     gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;
     ```
  2. Внедрить генерацию и сквозную передачу `$request_id`:
     ```nginx
     # Генерация уникального request_id на входе в систему
     proxy_set_header X-Request-ID $request_id;
     add_header X-Request-ID $request_id always;
     ```
  3. Синхронизировать формат `access_log` Nginx с логами бэкенда, включив поле `request_id=$request_id`.

---

### TASK-P05: University Contact Model OrganizationContact Normalization
- **Цель:** Устранить юридическую неопределенность контрагентов и привести контактную модель к эталону `docs/architecture/02-data-and-workflow.md`.
- **Инженерное решение:**
  1. Расширить модель `OrganizationContact`:
     - `email`: увеличить длину до `String(320)` в соответствии со стандартом RFC 5321.
     - Добавить поля: `notes Text`, `created_at DateTime`, `updated_at DateTime`, `revision Integer default 1`, `archived_at DateTime nullable`.
     - Создать составной индекс `Index("ix_org_contacts_active", "organization_id", "archived_at")`.
  2. Внедрить промежуточные таблицы связей (Junction Tables) для перехода от 1:1 к 1:N:
     - `interaction_contacts`: связь карточки с несколькими контактами вуза (куратор, ректор, декан) с указанием роли `role String(40)` и флага `is_primary Boolean`.
     - `interaction_contracts`: связь с договорами.
     - `interaction_licenses`: связь с лицензиями.
  3. Обновить сериализацию в `services.py` и компоненты отображения в `InteractionPage.tsx`.

---

## 4. Horizon Gate O: Промышленная эксплуатация / Масштабирование (Задачи P2)

| ID | Наименование задачи | Исполнитель | Трудозатраты | Целевой контур |
|:---:|---|:---:|:---:|---|
| **TASK-O01** | Process Decoupling — Redis, Celery & Outbox | Dev A + Dev B | 6–10 дн. | `compose.yaml`, `backend/app/tasks/` |
| **TASK-O02** | Global Access Policy Epoch (`authz_epoch`) | Dev A | 3–5 дн. | `backend/app/models.py`, `backend/app/services.py` |
| **TASK-O03** | Normalization of Temporal Fact Tables | Dev A + Dev B | 5–8 дн. | `backend/app/models.py`, `reports.py` |
| **TASK-O04** | ClamAV Antivirus Daemon via Streaming Socket | Dev A | 3–5 дн. [ЗАВЕРШЕНО] | `deploy/clamav/`, `backend/app/files.py` |

---

### TASK-O01: Process Decoupling — Redis Broker, Celery/RQ Workers & Transactional Outbox
- **Пять эмпирических пороговых критериев перехода на Celery + Redis:**  
  В соответствии с доменным аудитом `domain-07-performance.md:332-365`, синхронная модель AnyIO эффективна до определенных физических пределов. Переход на асинхронную распределенную очередь становится **безусловно обязательным** при наступлении любого из 5 событий:

```
                        5 КОЛИЧЕСТВЕННЫХ ТРИГГЕРОВ GATE O
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ 1. Объём данных:    > 10 000 карточек  ИЛИ  > 50 000 темпоральных событий│
  │ 2. Время отклика:   Длительность генерации отчёта > 2.0–3.0 с (P95 > 2с) │
  │ 3. Конкурентность:  > 20 параллельных экспортов ИЛИ утилизация AnyIO >75%│
  │ 4. Потребление RAM: RSS > 150 МБ на отчёт  ИЛИ всплеск экспорта > 500 МБ │
  │ 5. Изоляция 152-ФЗ: Развертывание очереди ──> Обязателен authz_epoch     │
  └──────────────────────────────────────────────────────────────────────────┘
```

1. **Критерий 1 (Dataset Volume):** Выборка превышает **10 000 взаимодействий** (`visible_ids`) или **50 000 темпоральных событий** (`InteractionEvent`). В памяти Python расчет превысит 2 секунды.
2. **Критерий 2 (Latency & Timeout):** Время генерации отчета превышает **2.0–3.0 секунды** (P95 > 2.0 с). Возникает риск разрыва соединения Nginx по таймауту с кодом `HTTP 504 Gateway Timeout`.
3. **Критерий 3 (Concurrency & GIL Contention):** Одновременный запуск более **20 тяжелых экспортов** или утилизация лимитера AnyIO свыше 75% (> 90 занятых токенов).
4. **Критерий 4 (Memory Footprint & OOM):** Потребление памяти процессом свыше **150 МБ RSS на один отчет** или суммарный транзиентный скачок свыше **500 МБ RAM**. Celery изолирует утечки через `--max-memory-per-child=200000`.
5. **Критерий 5 (152-FZ Isolation):** Непосредственно факт развертывания асинхронной очереди. Ожидание в очереди создает окно рассинхронизации прав.

- **Инженерная реализация:**
  - Внедрение брокера Redis в `compose.yaml`.
  - Реализация таблиц `background_job` (`id`, `kind`, `status`, `progress`, `requester_id`, `created_at`) и `transactional_outbox`.
  - Паттерн `POST /reports -> HTTP 202 Accepted` с заголовком `Location: /api/v1/jobs/{job_id}`.
  - Поллинг статуса через `GET /jobs/{job_id}` с возвратом артефакта через приватный StoragePort.

---

### TASK-O02: Global Access Policy Epoch `access_policy_state.epoch` (`authz_epoch`)
- **Цель:** Исключить брешь в безопасности по 152-ФЗ при отложенном асинхронном выполнении задач в Celery.
- **Суть проблемы:** Если тяжелый аналитический отчет ожидает в очереди 15–30 секунд, права инициатора могут быть отозваны руководителем (например, сотрудника сняли с должности или исключили из подразделения). Если воркер выполнит задачу с правами на момент постановки в очередь, произойдет компрометация ПДн (нарушение ст. 7 152-ФЗ).
- **Инженерное решение:**
  1. Создать синглтон-таблицу `access_policy_state`:
     ```python
     class AccessPolicyState(Base):
         __tablename__ = "access_policy_state"
         singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
         epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
         updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
     ```
  2. При любом изменении прав (переназначение карточки, изменение `OrganizationAccess`, смена роли) выполнять атомарный инкремент:
     `UPDATE access_policy_state SET epoch = epoch + 1 WHERE singleton_id = 1`.
  3. При постановке фоновой задачи сохранять текущую `request_authz_epoch`.
  4. Перед началом генерации отчета воркер сверяет сохраненную эпоху с актуальной в СУБД: если `job.authz_epoch != current_epoch`, воркер немедленно отменяет задачу с кодом `REPORT_SCOPE_CHANGED` и уведомляет пользователя о необходимости повторного запроса.

---

### TASK-O03: Normalization of Temporal Fact Tables
- **Цель:** Материализация визитов состояний и слепков отчетов для устранения вычислений «на лету» по монолитному JSON-журналу.
- **Инженерное решение:**
  1. Создать реляционную таблицу `state_visit`:
     - `id`: UUID.
     - `interaction_id`: FK `interactions.id`.
     - `state`: наименование статуса.
     - `entered_at`: метка входа на этап.
     - `exited_at`: метка выхода (nullable для текущего этапа).
     - `duration_seconds`: вычисляемая длительность для контроля регламентов SLA.
  2. Создать таблицы замороженных датасетов отчетов (Frozen Datasets):
     - `report_run`: метаданные отчета, инициатор, фильтры, `knowledge_cutoff`, хеш датасета.
     - `report_row`: сериализованные строки среза данных. Позволяет мгновенно отдавать повторный экспорт в любом формате без повторного обращения к операционным таблицам.

---

### TASK-O04: ClamAV Antivirus Daemon via Streaming Socket (clamd)
- **Статус:** Успешно реализовано и закрыто (COMPLETED).  
  Интегрирован потоковый сокет ClamAV INSTREAM (`clamd`), изолированный сетевой сервис в `compose.yaml`, двухфазная валидация файлов `pending_scan -> clean / quarantined`, изолирование угроз с кодом `422 VIRUS_DETECTED`, 100% покрытие тестами `backend/tests/test_clamav.py`.
- **Цель:** Обеспечить антивирусный контроль в соответствии со строгими требованиями регулятора ФСТЭК при сохранении высокой производительности.
- **Инженерное решение:**
  1. Развернуть контейнер `clamav:latest` в изолированном сегменте `dmz_net`.
  2. Настроить потоковую передачу данных через команду `INSTREAM` сетевого сокета `clamd` (порт 3310): файл передается блоками байтов напрямую из памяти без промежуточной записи на диск хоста.
  3. Ввести двухфазный статус файла: `pending_scan -> clean / quarantined`.
  4. При обнаружении угрозы возвращать клиенту стандартизированную ошибку `422 VIRUS_DETECTED` с изолированием файла в карантинную директорию.

---

## 5. Responsibility Matrix & Execution Order (Матрица ответственности и порядок внедрения)

### 5.1. Распределение пакетов работ (Developer A vs Developer B)
На основе эталонного плана двух разработчиков (`docs/architecture/04-two-developer-roadmap.md`) зафиксировано строгое разделение 41 пакета работ (106–177 человеко-дней):

```
                   РАСПРЕДЕЛЕНИЕ НАГРУЗКИ (ROADMAP 04)
┌────────────────────────────────────────────────────────────────────────┐
│ РАЗРАБОТЧИК A (Backend, Infra, DB, Security)  ── 20 пакетов (55–92 дн.)│
│ РАЗРАБОТЧИК B (Frontend, Reports, UX, E2E)    ── 21 пакет  (51–85 дн.) │
│ СУММАРНЫЙ ОБЪЕМ ПРОЕКТА                       ── 41 пакет (106–177 дн.)│
└────────────────────────────────────────────────────────────────────────┘
```

#### Зона ответственности Разработчика A (20 пакетов):
- **Фаза F0 (Фундамент):**
  - `TD01` (2–3 дн.) — Контракты C01–C07, модель доступа и периодов.
  - `TD03` (3–5 дн.) — Извлечение модулей, внедрение Alembic и Unit of Work.
  - `TD05` (3–5 дн.) — Единая политика доступа, команды и аудит сессий.
  - `TD06` (3–5 дн.) — Celery, Redis, примитивы Outbox и Inbox.
- **Фаза F1 (Операционный контур):**
  - `TD08` (3–5 дн.) — Каталоги, контакты, договоры, лицензии, назначения и архив.
  - `TD10` (3–5 дн.) — Interaction, StateVisit, аудит-история и серверные фильтры.
  - `TD12` (3–5 дн.) — Закрытые файлы, карантин, StoragePort и приватная выдача.
  - `TD16` (4–6 дн.) — Сохраненные workflow: draft, validate, publish.
  - `TD18` (3–5 дн.) — Двухфазный перенос действующих карточек workflow v1->v2.
- **Фаза F2 (Отчетность и интеграции):**
  - `TD22` (4–6 дн.) — Оркестрация интеграций, дедупликация и канонический инбокс.
  - `TD23` (2–4 дн.) — Сетевой адаптер LMS Zion и сверка.
  - `TD24` (2–4 дн.) — Сетевой адаптер сайта Laravel и обработка заявок.
  - `TD26` (3–5 дн.) — Нормализация учебных фактов и когорт.
- **Фаза F3 (Приемка и сдача):**
  - `TD30` (2–4 дн.) — Сквозной контроль этапов воронки и завершенных циклов.
  - `TD33` (3–5 дн.) — Нагрузочные испытания (50 пользователей + 10 отчетов).
  - `TD34` (3–5 дн.) — Linux delivery, наблюдаемость, бэкапы и восстановление.
  - `TD36` (2–3 дн.) — Archi-модель, состав решения и Swagger OpenAPI.
  - `TD38` (3–5 дн.) — Аудит мер защиты с владельцем ИБ (152-ФЗ, ФСТЭК №117).
  - `TD39` (2–4 дн.) — Подготовка пилотных данных и тестовой среды.
  - `TD41` (2–3 дн.) — Эксплуатационный выпуск и передача в промышленный контур.

#### Зона ответственности Разработчика B (21 пакет):
- **Фаза F0 (Фундамент):**
  - `TD02` (2–3 дн.) — Каркас React features, клиент API и контрактные моки.
  - `TD04` (2–3 дн.) — Воспроизводимые проверки baseline, CI и E2E-окружение.
  - `TD07` (2–4 дн.) — Общий shell, формы, сохранение стейта и черновиков.
- **Фаза F1 (Операционный контур):**
  - `TD09` (2–4 дн.) — Каталоги, карточка организации и назначения в UI.
  - `TD11` (2–4 дн.) — Реестр карточек, история визитов и граф процесса.
  - `TD13` (1–2 дн.) — Вложения в статусах, прогресс-бар и валидация 25 МБ.
  - `TD14` (4–6 дн.) — Парсер XLS/XLSX, маппинг колонок и валидатор строк.
  - `TD15` (2–4 дн.) — 3-шаговый мастер импорта и протокол ошибок.
  - `TD17` (3–5 дн.) — Редактор и визуальная проверка графов workflow.
- **Фаза F2 (Отчетность и интеграции):**
  - `TD19` (4–6 дн.) — Исторический query engine и определения отчетов.
  - `TD20` (3–5 дн.) — Мультиформатный экспорт XLSX, PDF, JSON и диаграмм.
  - `TD21` (3–5 дн.) — Конструктор отчетов, выбор колонок и фильтры в UI.
  - `TD25` (2–3 дн.) — Интерфейс управления интеграциями и разрешения коллизий.
  - `TD27` (3–5 дн.) — Расчет учебных показателей R30 и эталонный тест AC31.
  - `TD28` (2–3 дн.) — Проверяемые SVG/Canvas диаграммы воронки и аналитики.
- **Фаза F3 (Приемка и сдача):**
  - `TD29` (2–3 дн.) — UI администрирования прав, команд и назначений.
  - `TD31` (2–3 дн.) — Интерфейс мониторинга фоновых заданий (Jobs UI).
  - `TD32` (3–5 дн.) — Сквозная E2E-регрессия и стресс-тесты на отказ.
  - `TD35` (2–4 дн.) — Встроенные иллюстрированные руководства со скриншотами.
  - `TD37` (2–3 дн.) — Конкурсный демонстрационный комплект и репетиция защиты.
  - `TD40` (3–5 дн.) — Ограниченный пилот с пользователями и исправление замечаний.

---

### 5.2. Оптимальная пошаговая последовательность реализации Gate D
Для исключения конфликтов слияния, взаимных блокировок и падения автоматических оракулов проверки, исправления Gate D выполняются строго в следующем порядке:

```
                  ПОШАГОВЫЙ ПОРЯДОК ВНЕДРЕНИЯ GATE D
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Шаг 1: TASK-D04 ─ Dockerfile Non-Root (Изолированное изменение)        │
 │ Шаг 2: TASK-D02 ─ Nginx CSP https:/wss: (Конфигурация инфраструктуры)  │
 │ Шаг 3: TASK-D03 ─ Nginx 26m & CI Oracle (Атомарная синхронизация)      │
 │ Шаг 4: TASK-D01 ─ AnyIO 120 & QueuePool 120 (Синхронизация многопоточки│
 │ Шаг 5: TASK-D06 ─ Teams Table & Pre-Seeding (БД и целостность тестов)  │
 │ Шаг 6: TASK-D05 ─ Attachments Idempotency, CAS & UI FormData Sync      │
 └────────────────────────────────────────────────────────────────────────┘
```

#### Обоснование последовательности шагов:
1. **Шаг 1 (TASK-D04):** Замена строки в `backend/Dockerfile` не затрагивает исполняемый код и моментально закрывает замечание CIS Docker Benchmark.
2. **Шаг 2 (TASK-D02):** Добавление `https:` и `wss:` в `deploy/nginx.conf` изолировано и не влияет на тесты бэкенда.
3. **Шаг 3 (TASK-D03):** Атомарная правка `deploy/nginx.conf` (`26m`) и `docs/checks/verify_infra.py:68, 77` выполняется в одном коммите, гарантируя зеленый статус оракула инфраструктуры.
4. **Шаг 4 (TASK-D01):** Синхронное обновление AnyIO limiter (`total_tokens = 120`) и `QueuePool` (30 + 90 = 120 соединений) исключает как исчерпание потоков, так и дедлоки СУБД.
5. **Шаг 5 (TASK-D06):** Добавление модели `Team` и внешнего ключа `ForeignKey("teams.id")` выполняется строго с предварительным наполнением (pre-seeding) команд в `seed.py` и фикстурах, что гарантирует прохождение полного сьюта из 184 тестов.
6. **Шаг 6 (TASK-D05):** Завершающий шаг, требующий согласованного взаимодействия Dev A и Dev B: синхронное добавление `expected_revision` в `FormData` во фронтенде и поддержка `expected_revision: int | None = Form(None)` на бэкенде.

---

## 6. Verification, Invariants & Integrity Checklist (Верификация и целостность)

### 6.1. Автоматизированные проверочные команды
После выполнения каждого шага инженерного плана в обязательном порядке запускаются проверочные скрипты:

1. **Проверка инфраструктуры и безопасности:**
   ```bash
   python3 docs/checks/verify_infra.py
   # Ожидаемый результат: ALL INFRASTRUCTURE AND DEVSECOPS CHECKS PASSED.
   ```
2. **Проверка рабочего среза бизнес-логики:**
   ```bash
   backend/.venv/bin/pytest backend/tests/test_working_slice.py
   # Ожидаемый результат: 17 passed
   ```
3. **Проверка графа процесса FSM:**
   ```bash
   python3 docs/checks/verify_workflow.py
   # Ожидаемый результат: PASS: workflow definition is valid.
   ```
4. **Проверка аналитических отчетов:**
   ```bash
   python3 docs/checks/verify_reports.py
   # Ожидаемый результат: PASS: all 12 fixture assertions verified.
   ```
5. **Проверка плана разработки и матрицы требований:**
   ```bash
   python3 docs/checks/verify_plan.py
   # Ожидаемый результат: PASS: 40 tasks, 30 scenarios verified.
   ```
6. **Полный регрессионный сьют бэкенда:**
   ```bash
   backend/.venv/bin/pytest backend/tests/
   # Ожидаемый результат: 184 passed
   ```
7. **Компиляция фронтенда TypeScript (Zero Warnings / Zero Errors):**
   ```bash
   (cd frontend && pnpm build)
   # Ожидаемый результат: Successfully compiled without type errors.
   ```

---

### 6.2. Контроль неизменяемости эталонной архитектуры
Каталог `docs/architecture/*` является строго READ-ONLY:
```bash
git diff docs/architecture
# Вывод команды обязан быть абсолютно пустым!
```

---

### 6.3. Контроль побайтовой идентичности документов
Для передачи плана в смежные агентские контуры создается зеркальный дубликат:
- Основной документ: `docs/planning/audit/action-plan.md`
- Дубликат передачи: `.agents/action_plan_prioritizer/handoff.md`

Контроль 100% совпадения по контрольной сумме SHA-256:
```bash
sha256sum docs/planning/audit/action-plan.md .agents/action_plan_prioritizer/handoff.md
```
*(Оба файла обязаны иметь абсолютно идентичный хэш).*
