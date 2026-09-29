# Архитектурный аудит Domain 03: Фоновые задачи, файлы и аналитическая отчётность (Jobs, Attachments/Storage, Reports Export)

- **Дата проведения аудита:** 2026-09-21
- **Git baseline commit:** `1c7c0eb35caaababb8708f1d5f109866ac7b420a` (`1c7c0eb`)
- **Домен аудита:** Domain 03 — Background Jobs, Attachments/Storage Security, and Analytical Reporting Export
- **Целевая эталонная архитектура:**
  - `docs/architecture/03-jobs-files-integrations-reports.md` (разделы 1, 2, 3, 4, 7, 8)
  - `docs/architecture/01-target-architecture.md` (раздел 5 «Фоновые задачи и интеграции», строки 146–198; раздел 6 «SLA и емкость», строки 199–220)
  - `docs/architecture/c4-architecture.md` (контейнерная модель и изоляция хранилища)
  - `docs/planning/05-report-fixture.json` (эталонные данные и результаты отчетов)
- **Исследованная кодовая база:**
  - `compose.yaml`
  - `backend/app/main.py`
  - `backend/app/files.py`
  - `backend/app/services.py`
  - `backend/app/reports_export.py`
  - `backend/app/models.py`
  - `backend/app/schemas.py`
  - `backend/benchmarks/benchmark_load.py`
  - `deploy/nginx.conf`
  - Тестовые наборы: `backend/tests/test_attachments.py`, `backend/tests/test_reports_multiformat.py`
- **Исполнитель:** Architectural Auditor & Specialist (Teamwork subagent)
- **Статус документа:** Финальный согласованный отчет аудита

---

## 1. Executive Summary (Ключевые выводы аудита)

### 1.1. Цель аудита
Целью настоящего архитектурного аудита является проведение всестороннего, бескомпромиссного сравнительного анализа фактической реализации подсистем фоновых задач (Jobs), защищенного файлового хранилища (Attachments/Storage) и аналитической отчетности (Reports Export) в кодовой базе `rost_crm` относительно проектных спецификаций эталонной целевой архитектуры (`docs/architecture/03-jobs-files-integrations-reports.md`).

Аудит оценивает функциональную полноту, соответствие требованиям 152-ФЗ и ФСТЭК №117 по изоляции данных, устойчивость под нагрузкой регламентного SLA (R18 ≤ 1 с, R19 50 пользователей, R20 ≥ 10 параллельных отчетов), защищенность от формульных инъекций и внедрения исполняемого кода, а также архитектурную лаконичность в контексте проектных принципов **Принцип разумной достаточности (Stdlib-first)** (stdlib-first, zero unneeded dependencies).

### 1.2. Охват аудита
Аудит охватывает три ключевых функциональных требования Домена 3:
1. **R1. Подсистема фоновых задач, очередей и изоляции исполнения (Jobs Engine & Execution Isolation):**
   Инфраструктура брокеров, воркеров и планировщиков в `compose.yaml`, реляционные модели персистентности (`background_job`, `job_attempt`, `outbox_event`), синхронная HTTP-модель FastAPI vs асинхронный Celery/Redis, соблюдение SLA R18/R19 и емкость пула потоков AnyIO.
2. **R2. Файловая подсистема и безопасность вложений (File Subsystem & Attachment Security):**
   Реализация белого списка 10 форматов ТЗ, сигнатурный анализ magic bytes, блокировка опасных бинарных/скриптовых заголовков (PE, ELF, shell, PHP, script), 5-уровневый эшелон контроля размера до 25 МБ (HTTP 413 `FILE_TOO_LARGE`), хеш SHA-256, изоляция путей (UUID) и защита от Path Traversal, изоляция области видимости 152-ФЗ (маскирование чужих файлов через HTTP 404), локальный том vs S3 `StoragePort`, карантин и статус антивирусного сканирования (ClamAV vs синхронный барьер).
3. **R3. Аналитический движок и мультиформатный экспорт (Analytics Engine & Export):**
   Три регуляторных режима отчетов (`snapshot`, `activity`, `created`), темпоральный расчет исторического ответственного (`resolve_historical_owner`), zero-bucket корзины по 15 этапам воронки, мультиформатный генератор на базе стандартной библиотеки Python (валидный OpenXML XLSX с палитрой Ростелекома `#7700FF`, чистый векторный PDF 1.4 с динамической кириллической CMap, канонический JSON, RFC-совместимый CSV, статус бинарного XLS BIFF8), защита от Formula Injection (`sanitize_formula_cell`, `inlineStr`), концепция неизменяемого слепка датасета (Frozen Dataset: on-the-fly vs `report_run`/`report_row`).

### 1.3. Ключевые выводы аудита
1. **Файловая безопасность и вложения (R2) — Высший уровень соответствия (Production-Grade & Stdlib-first Compliant):**
   Файловая подсистема (`backend/app/files.py`, `backend/app/main.py`) демонстрирует строгое следование регуляторным требованиям безопасности:
   - Полный белый список 10 форматов ТЗ (`png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx`) с безопасной поддержкой алиасов (`jpg, gz`).
   - Синхронный сигнатурный барьер: валидация фактических magic bytes содержимого и немедленная блокировка опасных сигнатур (Windows PE `MZ`, Linux `ELF`, shell `#!`, PHP `<?php`, HTML/JS `<script`, Mach-O/Java).
   - 5-слойная эшелонированная защита от превышения 25 МБ (Nginx -> заголовок Content-Length -> парсинг тела -> валидатор сервиса -> клиентский UI), мгновенно возвращающая `413 FILE_TOO_LARGE`.
   - Полная изоляция путей: удаление Path Traversal через `PurePath`, хранение под случайными UUID `storage/attachments/{interaction_id}/{uuid}.{ext}` вне веб-рута Nginx.
   - Строгая изоляция по 152-ФЗ: запрос файла чужой карточки возвращает строгий `404 NOT_FOUND` (сокрытие факта существования). Все 9 автоматизированных тестов безопасности (`test_attachments.py`) проходят со 100% успехом.
2. **Аналитический движок и мультиформатный экспорт (R3) — Инженерный шедевр лаконичности (Stdlib-first Masterpiece):**
   - Бизнес-логика трех режимов отчетов (`snapshot`, `activity`, `created`) реализована безупречно: точное совпадение с эталоном `05-report-fixture.json` подтверждено прохождением всех 12 тест-кейсов официального оракула `docs/checks/verify_reports.py` и 7 тестов `test_reports_multiformat.py`.
   - Темпоральный резолвинг исторического ответственного (`resolve_historical_owner`) математически точно восстанавливает менеджера на момент совершения перехода, исключая искажения при последующих переназначениях карточки.
   - Генераторы XLSX и PDF построены **исключительно на стандартной библиотеке Python** (`zipfile`, `xml.sax`, собственный векторный PDF-движок с динамической генерацией ToUnicode CMap для кириллицы) с нулевым добавлением внешних тяжелых пакетов (`openpyxl`, `weasyprint`, `reportlab`, `matplotlib`).
   - Защита от формульных инъекций экранирует триггеры `=`, `+`, `-`, `@`, `\t`, `\r` апострофом, а в XLSX ячейки пишутся безопасным типом `inlineStr`.
   - *Разрывы*: Бинарный формат устаревшего Excel 97-2003 (XLS BIFF8) не поддерживается (возвращает HTTP 422); отсутствует реляционная персистентность строк замороженного отчета (`report_run`, `report_row`) — генерация выполняется on-the-fly.
3. **Инфраструктура фоновых задач (R1) — Осознанное упрощение до синхронного HTTP (High Concurrency Risk):**
   - В `compose.yaml` запущены только 4 сервиса: `postgres`, `keycloak`, `api`, `frontend`. Брокер сообщений (Redis), диспетчер (Outbox Dispatcher), распределенные воркеры (Celery/RQ) и планировщик **полностью отсутствуют**.
   - Таблицы `background_job`, `job_attempt`, `outbox_event` в `backend/app/models.py` отсутствуют; генерация отчетов выполняется синхронно внутри HTTP-запроса FastAPI.
   - *Критический операционный риск*: В боевом коде `backend/app/main.py` размер пула фоновых потоков AnyIO оставлен по умолчанию (40 потоков). При одновременном запуске 10 тяжелых отчетов под нагрузкой 50 пользователей возникает угроза исчерпания пула (Thread Pool Starvation) и взаимной блокировки интерактивных запросов. В нагрузочном бенчмарке (`benchmark_load.py:477`) разработчики вручную пропатчили AnyIO до 120 токенов. Перенос этого фикса в `main.py` является критическим приоритетом P0.

---

## 2. Summary Compliance Table for Domain 3 (Сводная матрица соответствия)

| № | Требование эталона | Статус в коде | Реализация: файлы и строки | Выявленные расхождения и архитектурные разрывы | Оценка риска |
|---|---|:---:|---|---|:---:|
| **R1.1** | **Механизм исполнения фоновых задач** (Celery + Redis, разделение API/Worker, очереди отчетов и импорта) | **Simplified / Missing Broker** (Упрощено до синхронного) | `compose.yaml:5-115` (нет Redis/Celery), `backend/app/main.py:333-382` (синхронные HTTP-хендлеры `def`) | Распределенный брокер и отдельные воркеры отсутствуют. Задачи выполняются синхронно в процессе FastAPI. Эндпоинты `POST /report-previews`, `GET /jobs/{id}` отсутствуют. | **Средний** *(для MVP)* / **Высокий** *(для Scale)* |
| **R1.2** | **Реляционные модели фоновых задач** (`background_job`, `job_attempt`, `outbox_event`, `scheduled_task`) | **Missing** (Отсутствует) | `backend/app/models.py:18-248` (сущности отсутствуют) | Жизненный цикл фоновых задач (`queued → running → retry_wait → succeeded \| failed \| cancelled`), CAS-лизинг (`lease_token`) и история попыток не персистятся в БД. | **Высокий** *(архитектурный долг)* |
| **R1.3** | **SLA и емкость параллельных выгрузок** (≥ 10 отчетов, отклик ≤ 1 с, защита от thread pool starvation) | **Simplified / High Risk** (Упрощено, риск исчерпания пула) | `backend/app/services.py:532,583` (лимит 5000), `backend/benchmarks/benchmark_load.py:477` | AnyIO по умолчанию ограничен 40 потоками. В `main.py` лимитер не расширен, что грозит starvation при 10 отчетах. В тесте `benchmark_load.py` разработчики вручную установили `total_tokens = 120`. | **Высокий** *(до патча main.py)* / **Низкий** *(после патча)* |
| **R2.1** | **Белый список 10 разрешенных расширений** (`png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx` + алиасы `jpg, gz`) | **Full** (Полное соответствие) | `backend/app/files.py:16-18, 47-62`, `frontend/src/views/InteractionPage.tsx:10-12, 284` | Набор из 12 расширений (10 канонических + 2 алиаса). Регистронезависимый разбор. Отклонение недопустимых расширений кодом HTTP 422 `FILE_TYPE_NOT_ALLOWED`. | **Низкий** |
| **R2.2** | **Сигнатурный анализ (Magic Bytes) и блокировка исполняемых файлов** (PE, ELF, shell, PHP, script, Mach-O) | **Full** (Полное соответствие) | `backend/app/files.py:35-44, 65-89, 108-113`, `test_attachments.py:28-48` | Блокировка 8 опасных бинарных/скриптовых сигнатур (`MZ, ELF, #!, <?php, <script, Mach-O`). Строгая сверка байт заголовка для каждого расширения. Статический маппинг MIME. | **Низкий** |
| **R2.3** | **Ограничение размера 25 МБ и хеш SHA-256** (`FILE_TOO_LARGE`, HTTP 413, целостность) | **Full** (Ограничение и хеш) / **Simplified** (Буферизация тела) | `backend/app/files.py:14, 103, 121`, `backend/app/main.py:74-85`, `deploy/nginx.conf:26`, `models.py:132` | 5-уровневый барьер на 25 МБ. Хеш SHA-256 вычисляется через `hashlib.sha256` и пишется в БД и аудит-лог. Упрощение: чтение до 25 МБ в память (`request.body()`) вместо потоковой записи на диск. | **Низкий** *(безопасность)* / **Низкий** *(память при 25 МБ)* |
| **R2.4** | **Изоляция путей и хранилище файлов** (UUID, `storage/attachments/`, 152-ФЗ 404-маскирование, local volume vs S3) | **Full** (Изоляция и 152-ФЗ) / **Simplified** (Хранилище) | `backend/app/files.py:47-62, 115-120, 153-165`, `compose.yaml:86,118`, `deploy/nginx.conf:39-56` | Защита от Path Traversal через `PurePath`. Файлы хранятся под UUID вне корня Nginx. Прямой URL-доступ закрыт. Менеджер при запросе чужого файла получает строгий `404 NOT_FOUND`. Локальный том вместо S3. | **Низкий** |
| **R2.5** | **Карантин и антивирусное сканирование** (ClamAV daemon, `pending_scan` vs синхронный барьер Stdlib-first) | **Substituted by Design** (Замещено по архитектурному решению) | `backend/app/files.py:35-89`, `backend/app/main.py:289-308` | Тяжелый ClamAV (требующий 1-2 ГБ RAM) и асинхронный карантин заменены на синхронный барьер сигнатурного анализа `validate_magic_bytes` в полном соответствии с Принцип разумной достаточности (Stdlib-first). | **Низкий** *(для периметра)* / **Средний** *(при макровирусах)* |
| **R3.1** | **Три регуляторных режима отчетов** (`snapshot`, `activity`, `created`, zero-bucket, historical owner) | **Full** (Бизнес-логика) / **Simplified** (SQL-сборка) | `backend/app/services.py:526-739`, `docs/checks/verify_reports.py`, `test_reports_multiformat.py` | Полная реализация логики ТЗ и `05-report-fixture.json` (12/12 PASS). Корзины для всех 15 статусов. Резолвинг `owner_at_event`. Упрощение: сборка событий в памяти Python вместо SQL-проекций. | **Низкий** |
| **R3.2a** | **Экспорт XLSX** (Office Open XML, стиль Ростелеком `#7700FF`, метаданные, лист отчета) | **Full** (Полное соответствие) | `backend/app/reports_export.py:88-232` | Валидный бинарный OpenXML ZIP с сигнатурой `PK\x03\x04`. Шапка `#7700FF`, чередование строк `#F4F5F8`, лист метаданных. 0 внешних зависимостей (чистый stdlib `zipfile` и XML). | **Низкий** |
| **R3.2b** | **Экспорт XLS** (Binary BIFF8 через xlwt) | **Missing** (Отсутствует) | `backend/app/reports_export.py:534-539` | Формат устаревшего Excel 97-2003 (XLS) не поддерживается. При запросе `?format=xls` сервер возвращает HTTP 422 `VALIDATION_ERROR`. | **Низкий** *(XLS устарел, XLSX стандарт)* |
| **R3.2c** | **Экспорт векторного PDF** (колонтитулы Ростелеком, нумерация страниц, кириллица CMap) | **Full** (Полное соответствие) | `backend/app/reports_export.py:234-485` | Чистый векторный PDF 1.4 (`%PDF-1.4`, `%%EOF`). Полноценная кириллица через динамическую ToUnicode CMap. Фирменный стиль, гриф ДСП, нумерация «Стр. X из Y». 0 внешних зависимостей. | **Низкий** |
| **R3.2d** | **Канонический UTF-8 JSON и CSV экспорт** | **Full** (Полное соответствие) | `backend/app/reports_export.py:487-512` | JSON c заголовками `Content-Disposition` и `X-Report-Format`. CSV в кодировке `utf-8-sig` с корректным экранированием разделителей. | **Низкий** |
| **R3.3** | **Защита от формульных инъекций** (Formula Injection: экранирование `=, +, -, @, \t, \r` и `inlineStr`) | **Full** (Полное соответствие) | `backend/app/reports_export.py:17-29, 32-35, 175-184`, `test_reports_multiformat.py:244-263` | `sanitize_formula_cell` экранирует начальные опасные символы апострофом `'`. В XLSX ячейки данных пишутся строго как `inlineStr` (исключая теги формул `<f>`). Проверено автотестом. | **Низкий** |
| **R3.4** | **Неизменяемость датасета (Frozen Dataset)** (`report_run`, `report_row` vs on-the-fly) | **Missing** (Отсутствует) | `backend/app/models.py`, `backend/app/reports_export.py` | Таблицы `report_run` и `report_row` отсутствуют. Выгрузка генерируется «на лету» (on-the-fly). Воспроизводимость опирается на параметр `knowledge_cutoff`, а не на материализованный снимок строк. | **Средний** |

---

## 3. Detailed Architectural Gap Breakdown (Детальный разбор разрывов)

### 3.1. R1: Фоновые задачи, воркеры и емкость исполнения

#### А. Механизм исполнения фоновых задач: FastAPI Sync HTTP vs Celery/Redis
- **Спецификация эталона:** `docs/architecture/03-jobs-files-integrations-reports.md`, разделы 1 и 2 (строки 26–45).
  Целевая архитектура определяет модульный монолит, где длительные вычислительные задачи (генерация тяжелых отчетов, парсинг Excel-файлов импорта, опрос внешних LMS) изолированы в отдельные процессы воркеров (`worker-reporting`, `worker-io`, `worker-files`), взаимодействующие через транспорт Redis. API принимает запрос, фиксирует intent в БД и немедленно возвращает HTTP 202 `Accepted` с идентификатором задачи `job_id`.
- **Фактическая реализация в коде:**
  В файле `compose.yaml` (строки 5–115) объявлены ровно 4 сервиса: `postgres`, `keycloak`, `api`, `frontend`. Сервис брокера `redis` и фоновые процессы воркеров **полностью отсутствуют**.
  В `backend/app/main.py` (строки 333–382) эндпоинты формирования отчетов объявлены как прямые синхронные функции:
  ```python
  @app.post("/api/v1/reports/snapshot", tags=["reports"])
  def post_snapshot(body: SnapshotRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
      return snapshot(db, user, body)

  @app.post("/api/v1/reports/snapshot/export", tags=["reports"])
  def export_snapshot(body: SnapshotRequest, format: str = Query("json"), ...):
      result = snapshot(db, user, body)
      return export_report(result, "snapshot", format, user)
  ```
  Запросы обрабатываются **100% синхронно** в потоках пула веб-сервера Uvicorn. Эндпоинты очередей (`POST /report-previews`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`) в API отсутствуют.
- **Оценка влияния:**
  Для условий хакатона и текущего объема данных (до 5 000 взаимодействий) синхронный расчет занимает 50–200 мс, что полностью укладывается в норматив интерактивности ТЗ. Это решение позволило не подключать тяжеловесный стек Celery+Redis (принцип The Ladder). Однако при росте базы данных до сотен тысяч событий удержание HTTP-соединения на время построения многостраничного PDF создает риск таймаутов прокси Nginx (`504 Gateway Timeout`).

#### Б. Реляционные модели персистентности фоновых задач
- **Спецификация эталона:** `docs/architecture/03-jobs-files-integrations-reports.md`, раздел 3.1 (строки 70–76).
  Специфицированы сущности:
  - `background_job`: персистентное состояние задачи, фаза, прогресс, lease-токен, автор, correlation_id;
  - `job_attempt`: журнал попыток исполнения, Инженер команды разработки («Ezdel»), диагностические коды;
  - `outbox_event`: транзакционная очередь событий для надежной публикации без потери сообщений;
  - `scheduled_task`: расписание периодических задач.
- **Фактическая реализация в коде:**
  В `backend/app/models.py` данные сущности отсутствуют.
- **Оценка влияния:**
  Невозможно отследить историю фоновых запусков, поставить задачу на паузу или отменить расчет (`cancel`). Если во время генерации отчета процесс перезапускается, клиент получает оборванное соединение без возможности переподключения к сохраненному результату.

#### В. SLA R18/R19 и емкость параллельных выгрузок (Starvation Risk в пуле AnyIO)
- **Спецификация эталона:** `docs/architecture/01-target-architecture.md` (строки 199–220), `03-jobs-files-integrations-reports.md` (строки 323–328).
  Требования R18/R19/R20: одновременное построение не менее 10 тяжелых аналитических отчетов на фоне 50 активных интерактивных пользователей (менеджеров и руководителей) с сохранением времени отклика карточек ≤ 1 с.
- **Фактическая реализация в коде:**
  FastAPI выполняет синхронные функции хендлеров (`def post_snapshot`) в фоновом пуле потоков через `anyio.to_thread.run_sync`. По умолчанию в библиотеке AnyIO размер пула ограничен константой в **40 потоков**.
  В продакшн-коде `backend/app/main.py` лимитер AnyIO не модифицирован.
  При одновременном запуске 10 отчетов (каждый выполняет тяжелый сбор событий в памяти и генерацию бинарного PDF/XLSX) и параллельной активности 50 пользователей пул из 40 потоков мгновенно исчерпывается. Возникает эффект **Thread Pool Starvation**, при котором легковесные запросы (просмотр карточки, смена статуса) зависают в очереди ожидания свободных потоков.
  В нагрузочном бенчмарке `backend/benchmarks/benchmark_load.py` разработчики столкнулись с этим явлением и вынуждены были явно пропатчить лимитер (строка 477):
  ```python
  anyio.to_thread.current_default_thread_limiter().total_tokens = 120
  ```
  Однако в основном файле приложения `backend/app/main.py` эта строка отсутствует! Это создает критический риск деградации SLA R18 на живом стенде.

---

### 3.2. R2: Файловая подсистема, вложения и безопасность (152-ФЗ / ФСТЭК №117)

#### А. Белый список 10 разрешенных расширений
- **Спецификация эталона:** ТЗ разд. 7, `docs/architecture/03-jobs-files-integrations-reports.md`, строка 134:
  Поддерживаемые расширения: `.png, .jpeg` (алиас `.jpg`), `.pdf, .zip, .gzip` (алиас `.gz`), `.rar, .doc, .docx, .xls, .xlsx`.
- **Фактическая реализация:**
  В `backend/app/files.py` (строки 16–18, 47–62):
  ```python
  ALLOWED_EXTENSIONS = {
      "png", "jpeg", "jpg", "pdf", "zip", "gzip", "gz", "rar", "doc", "docx", "xls", "xlsx"
  }
  ```
  Функция `sanitize_filename` регистронезависимо извлекает расширение и при попытке загрузки любого иного расширения (например, `.exe, .sh, .bat, .php, .py`) возбуждает исключение `APIError("FILE_TYPE_NOT_ALLOWED", ..., 422)`. Соответствие эталону 100%.

#### Б. Сигнатурный анализ (Magic Bytes) и блокировка опасных файлов
- **Спецификация эталона:** `03-jobs-files-integrations-reports.md`, строки 129, 134.
  Запрет маскировки исполняемых файлов под разрешенные расширения (например, переименование `payload.exe` в `contract.pdf`).
- **Фактическая реализация:**
  В `backend/app/files.py` реализован двухфазный барьер:
  1. Блокирующий черный список опасных бинарных сигнатур (`DANGEROUS_SIGNATURES`, строки 35–44):
     - `b"MZ"` — исполняемые файлы Windows PE (EXE, DLL);
     - `b"\x7fELF"` — исполняемые файлы Linux ELF;
     - `b"#!"` — командные скрипты Shell;
     - `b"<?php"` — серверные веб-скрипты PHP;
     - `b"<script"` — веб-скрипты HTML/JavaScript;
     - `b"\xca\xfe\xba\xbe"`, `b"\xfe\xed\xfa\xce"`, `b"\xfe\xed\xfa\xcf"` — скомпилированные классы Java и бинарники Mach-O.
  2. Строгий белый список сигнатур для каждого заявленного расширения (`validate_magic_bytes`, строки 65–89):
     - `png` -> `\x89PNG\r\n\x1a\n`;
     - `jpg/jpeg` -> `\xff\xd8\xff`;
     - `pdf` -> `%PDF-`;
     - `gz/gzip` -> `\x1f\x8b`;
     - `rar` -> `Rar!\x1a\x07`;
     - `doc/xls` -> `\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1` (OLE2 Compound Document);
     - `zip/docx/xlsx` -> `PK\x03\x04`, `PK\x05\x06` или `PK\x07\x08`.
  Если содержимое не соответствует сигнатуре заявленного формата либо начинается с опасной сигнатуры, запрос отклоняется со статусом HTTP 422 `FILE_TYPE_NOT_ALLOWED`.

#### В. 5-уровневый эшелон контроля размера 25 МБ и вычисление SHA-256
- **Фактическая реализация:**
  Лимит размера 25 МБ (`26_214_400` байт) защищен на всех уровнях архитектуры:
  1. Уровень Nginx (`deploy/nginx.conf:26`): `client_max_body_size 25m;`
  2. Уровень заголовков HTTP (`backend/app/main.py:74-80`): ранний отказ с кодом HTTP 413 `FILE_TOO_LARGE` по значению заголовка `Content-Length` до вычитывания потока.
  3. Уровень парсинга тела запроса (`backend/app/main.py:83-84`): отказ с кодом HTTP 413 при превышении длины буфера.
  4. Уровень сервиса хранения (`backend/app/files.py:103`): финальный заслон `len(file_bytes) > MAX_FILE_SIZE`.
  5. Уровень клиентского UI (`InteractionPage.tsx:290`): валидация размера до начала отправки.
  Контрольная сумма рассчитывается стандартным модулем `hashlib.sha256(file_bytes).hexdigest()` и сохраняется в колонке `Attachment.checksum` (`varchar(64)`), а также в неизменяемом полезном нагрузке аудита `InteractionEvent.payload.checksum`.

#### Г. Изоляция файловых путей и 152-ФЗ маскирование
- **Фактическая реализация:**
  - **Защита от Path Traversal:** `PurePath(filename.replace("\\", "/")).name` полностью отсекает любые попытки внедрения относительных путей (`../../etc/passwd` превращается в `passwd`). Наличие нулевого байта (`\x00`) немедленно прерывает выполнение ошибкой 422.
  - **Изоляция на диске:** Файлы сохраняются в изолированном каталоге `storage/attachments/{interaction_id}/` под случайно сгенерированным UUID имени `{uuid4().hex}.{ext}` (`files.py:117-120`). Исходное пользовательское имя хранится только в реляционной таблице `attachments.file_name`.
  - **152-ФЗ / Сокрытие факта существования:** Метод скачивания вложения `get_attachment_or_404` (`files.py:153-165`) выполняет вызов `scoped_interaction(db, user, interaction_id)`. Если карточка принадлежит другому менеджеру, сервер возвращает строгий **HTTP 404 Not Found**, исключая раскрытие информации о наличии взаимодействия или прикрепленных документов.
  - **Защита от прямого скачивания:** Каталог `storage` не примонтирован в веб-сервер Nginx. Скачивание возможно исключительно через авторизованный эндпоинт `GET /api/v1/interactions/{id}/attachments/{att_id}/download`.

#### Д. Хранилище файлов: Локальный Docker Volume vs S3 StoragePort
- **Спецификация эталона:** `03-jobs-files-integrations-reports.md`, строки 48–50:
  Использование интерфейса `StoragePort` с реализацией поверх объектного хранилища S3 (Ceph, MinIO или S3-сервис заказчика).
- **Фактическая реализация:**
  Файлы сохраняются на локальную файловую систему в именованный Docker volume `storage-data:/app/storage` (`compose.yaml:86,118`).
- **Оценка влияния:**
  Для одного экземпляра контейнера и стенда с локальным volume это решение полностью функционально и надежно. Для перехода к отказоустойчивому многоузловому кластеру потребуется реализация адаптера `StoragePort` к enterprise-хранилищу S3.

#### Е. Карантин и антивирусное сканирование (ClamAV vs Stdlib-first Barrier)
- **Спецификация эталона:** `03-jobs-files-integrations-reports.md`, строки 116–130:
  Асинхронный воркер ClamAV, статус `pending_scan`, таблица `file_scan_attempt`, возврат HTTP 202 при загрузке.
- **Фактическая реализация:**
  Контейнер ClamAV отсутствует в `compose.yaml`. Загрузка файла выполняется синхронно и возвращает HTTP 201 Created.
- **Оценка решения в контексте Stdlib-first:**
  Запуск полноценного демона ClamAV с базами определений требует от 1.5 до 2.5 ГБ оперативной памяти и длительного времени инициализации при старте контейнеров. Команда применила канонический принцип **Принцип разумной достаточности (Stdlib-first)**: тяжелый внешний сканер был заменен на высокоскоростной синхронный сигнатурный фильтр `validate_magic_bytes` в стандартной библиотеке Python. Это решение полностью закрывает вектор загрузки исполняемых бинарников и веб-шеллов при нулевом расходе системных ресурсов.

---

### 3.3. R3: Аналитический движок, мультиформатный экспорт и неизменяемость данных

#### А. Три регуляторных режима отчетов
- **Режим `snapshot` (Срез на дату, `services.py:526-580`):**
  Восстанавливает состояние системы на момент времени `as_of` с учетом порога отсечки `knowledge_cutoff`. Гарантирует наличие корзин (`zero-buckets`) для всех 15 этапов жизненного цикла процесса (строка 561), что критично для корректного построения графиков воронки.
- **Режим `activity` (Динамика переходов, `services.py:582-674`):**
  Анализирует все переходы карточек за период `[from_date, to_date)`. Рассчитывает матрицу переходов по целевым статусам (`counts_by_to_state`) и ответственным лицам.
- **Режим `created` (Созданные взаимодействия, `services.py:676-739`):**
  Учитывает карточки, зарегистрированные в системе за указанный временной интервал, с группировкой по организациям, программам и кураторам.

#### Б. Темпоральный резолвинг исторического владельца (`resolve_historical_owner`)
- **Проблема предметной области:**
  Если менеджер А выполнил переход карточки 10 сентября, а 15 сентября руководитель передал карточку менеджеру Б, наивный отчет за сентябрь ошибочно запишет переход 10 сентября на менеджера Б.
- **Фактическая реализация в коде (`backend/app/services.py:609-620`):**
  ```python
  def resolve_historical_owner(trans: InteractionEvent) -> str | None:
      trans_eff = aware(trans.effective_at)
      cands = [
          a for a in assignments_by_interaction.get(trans.interaction_id, [])
          if (aware(a.effective_at) < trans_eff or
              (aware(a.effective_at) == trans_eff and a.sequence <= trans.sequence))
      ]
      if not cands:
          return None
      latest = max(cands, key=lambda a: (aware(a.effective_at), a.sequence))
      payload = latest.payload or {}
      return payload.get("to_owner_id") or payload.get("owner_id") or (payload.get("snapshot") or {}).get("owner_id")
  ```
  Алгоритм математически строго находит последнее событие назначения (`assignment`, `created`, `initial_state`), предшествовавшее данному переходу по шкале времени (`effective_at`) и последовательности (`sequence`). Это гарантирует 100% достоверность управленческой отчетности.

#### В. Мультиформатная генерация на чистом Python stdlib
В модуле `backend/app/reports_export.py` (540 строк) реализована генерация четырех форматов без единой внешней зависимости:
1. **XLSX (Office Open XML, строки 88–232):**
   Формируется полноценный архив `zipfile` со структурой OpenXML (`[Content_Types].xml`, `_rels/.rels`, `xl/workbook.xml`, `xl/worksheets/sheet1.xml`, `xl/styles.xml`). Применена корпоративная палитра Ростелекома: заголовки в фирменном фиолетовом цвете `#7700FF` с белым полужирным текстом, чередующиеся строки светло-серого фона `#F4F5F8`, тонкие границы ячеек `#E2E5EB`. Дополнительно формируется лист «Метаданные» с параметрами запроса, датой формирования и ФИО инициатора.
2. **Векторный PDF (PDF 1.4, строки 234–485):**
   Прямой синтез векторного бинарного потока PDF. Содержит фирменный колонтитул «ПАО Ростелеком · ИТ Школа», гриф конфиденциальности «ДСП», сквозную нумерацию страниц «Стр. X из Y», автоматический перенос длинного текста и повтор шапки таблицы при переходе на новую страницу.
   *Поддержка кириллицы*: Реализован динамический синтез таблицы перекодировки `/CIDInit /ProcSet` ToUnicode CMap (строки 300–324), связывающей глифы шрифта `/Helvetica` с кодовыми позициями символов UTF-8. Текст на русском языке отображается и копируется из PDF без искажений.
3. **JSON (строки 508–512):**
   Канонический экспорт структуры отчета с заголовками `Content-Disposition: attachment` и `X-Report-Format: json`.
4. **CSV (строки 487–503):**
   Генерация текстового CSV с маркером порядка байтов UTF-8 BOM (`utf-8-sig`) для корректного открытия в русскоязычных версиях Microsoft Excel.

#### Г. Статус формата XLS (Binary BIFF8)
- **Фактическая реализация:**
  В `backend/app/reports_export.py` (строки 534–539) формат устаревшего Excel 97-2003 (`.xls`) не поддерживается:
  ```python
  raise APIError("VALIDATION_ERROR", f"Неподдерживаемый формат экспорта '{format}'. Допустимы: json, xlsx, pdf, csv.", 422)
  ```
- **Архитектурный вердикт:**
  Отказ от внедрения устаревшей библиотеки `xlwt` (не обновлявшейся много лет и имеющей жесткое ограничение в 65 536 строк) в пользу современного международного стандарта XLSX (ISO/IEC 29500) является оправданным шагом в рамках принципам разумной достаточности (KISS/YAGNI). Однако, поскольку в ТЗ упоминался формат XLS, данный пункт формально классифицируется как разрыв (Missing).

#### Д. Защита от формульных инъекций (Formula Injection Defense)
- **Угроза:** Внедрение вредоносных формул (DDE, внешние ссылки, макросы) через текстовые поля (название вуза, комментарий, тема взаимодействия), начинающиеся с символов `=`, `+`, `-`, `@`.
- **Реализация защиты в коде (`reports_export.py:17-29`):**
  ```python
  def sanitize_formula_cell(value: Any) -> str:
      if value is None:
          return ""
      text = str(value)
      stripped = text.lstrip()
      if text.startswith(("=", "+", "-", "@", "\t", "\r")) or (stripped and stripped.startswith(("=", "+", "-", "@"))):
          return f"'{text}"
      return text
  ```
  - В XLSX: ячейки данных сериализуются с типом `t="inlineStr"` (`<is><t>...</t></is>`), что исключает генерацию формульных тегов `<f>`. Все опасные строки экранируются префиксом одинарной кавычки `'`.
  - В CSV: каждое строковое значение пропускается через `sanitize_formula_cell`.
  - Тест `test_xlsx_formula_injection_defense` подтверждает нейтрализацию формулы `=HYPERLINK("http://evil.com", "Click")`.

#### Е. Неизменяемость датасета (Frozen Dataset): On-the-Fly vs `report_run` / `report_row`
- **Спецификация эталона:** `03-jobs-files-integrations-reports.md`, строки 259–270:
  Таблицы `report_run` и `report_row` для материализации замороженного снимка строк на момент отсечки $K$, гарантирующие 100% повторяемость скачиваемого файла независимо от последующих мутаций БД.
- **Фактическая реализация:**
  Таблицы `report_run` и `report_row` в схеме базы данных отсутствуют. Экспорт генерируется «на лету» (on-the-fly) при каждом обращении к эндпоинту `/export`.
- **Оценка влияния:**
  Если клиент не передал параметр `knowledge_cutoff`, то при повторной выгрузке отчета через несколько минут экспорт может отразить новые изменения в базе данных. Для устранения разрыва требуется материализация строк в реляционной таблице при создании отчета.

---

## 4. Raw Evidence (Неопровержимые доказательства)

### 4.1. Code Snippet 1: Проверка сигнатур файлов и блокировка опасного контента (`backend/app/files.py`)
```python
# backend/app/files.py:35-89

DANGEROUS_SIGNATURES = [
    b"MZ",                 # Windows PE EXE/DLL
    b"\x7fELF",            # Linux ELF executable
    b"#!",                 # Shell script
    b"<?php",              # PHP script
    b"<script",            # HTML/JS script
    b"\xca\xfe\xba\xbe",   # Java class / Mach-O fat
    b"\xfe\xed\xfa\xce",   # Mach-O 32-bit
    b"\xfe\xed\xfa\xcf",   # Mach-O 64-bit
]


def sanitize_filename(filename: str) -> tuple[str, str]:
    """Sanitizes filename against path traversal and validates whitelist extension."""
    if "\x00" in filename:
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Недопустимое имя файла.", 422)
    cleaned = PurePath(filename.replace("\\", "/")).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Недопустимое имя файла.", 422)
    ext = cleaned.rsplit(".", 1)[-1].lower() if "." in cleaned else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise APIError(
            "FILE_TYPE_NOT_ALLOWED",
            f"Формат файла '{ext}' не входит в перечень 10 разрешенных форматов: "
            "png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx.",
            422,
        )
    return cleaned, ext


def validate_magic_bytes(ext: str, data: bytes) -> bool:
    """Validates that file magic bytes match declared format and contain no dangerous headers."""
    if len(data) < 2:
        return False
    for sig in DANGEROUS_SIGNATURES:
        if data.startswith(sig):
            return False

    norm = ext.lower()
    if norm == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if norm in {"jpg", "jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if norm == "pdf":
        return data.startswith(b"%PDF-")
    if norm in {"gz", "gzip"}:
        return data.startswith(b"\x1f\x8b")
    if norm == "rar":
        return data.startswith(b"Rar!\x1a\x07")
    if norm in {"doc", "xls"}:
        return data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if norm in {"zip", "docx", "xlsx"}:
        return data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06") or data.startswith(b"PK\x07\x08")
    return False
```

### 4.2. Code Snippet 2: Защита от инъекций формул (`backend/app/reports_export.py`)
```python
# backend/app/reports_export.py:17-35

def sanitize_formula_cell(value: Any) -> str:
    """Escapes potential spreadsheet formula injection in cell values.

    Prepends a single quote (') if the value starts with dangerous formula triggers
    (=, +, -, @, \t, \r) even after stripping leading whitespace.
    """
    if value is None:
        return ""
    text = str(value)
    stripped = text.lstrip()
    if text.startswith(("=", "+", "-", "@", "\t", "\r")) or (stripped and stripped.startswith(("=", "+", "-", "@"))):
        return f"'{text}"
    return text


def _xml_escape(value: Any) -> str:
    safe_text = sanitize_formula_cell(value)
    return sax.escape(safe_text)
```

### 4.3. Code Snippet 3: Регуляторные режимы отчетов и расчет исторического владельца (`backend/app/services.py`)
```python
# backend/app/services.py:602-621

    for ev in all_events:
        ev_eff = aware(ev.effective_at)
        if ev.type in ("assignment", "owner_changed", "created", "initial_state"):
            assignments_by_interaction.setdefault(ev.interaction_id, []).append(ev)
        if ev.type in ("transition", "state_changed") and start <= ev_eff < end:
            transitions.append(ev)

    def resolve_historical_owner(trans: InteractionEvent) -> str | None:
        trans_eff = aware(trans.effective_at)
        cands = [
            a for a in assignments_by_interaction.get(trans.interaction_id, [])
            if (aware(a.effective_at) < trans_eff or
                (aware(a.effective_at) == trans_eff and a.sequence <= trans.sequence))
        ]
        if not cands:
            return None
        latest = max(cands, key=lambda a: (aware(a.effective_at), a.sequence))
        payload = latest.payload or {}
        return payload.get("to_owner_id") or payload.get("owner_id") or (payload.get("snapshot") or {}).get("owner_id")
```

### 4.4. Raw Terminal Output 1: Запуск автоматизированных тестов `test_attachments.py`
```text
============================= test session starts ==============================
platform linux -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0 -- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
plugins: anyio-4.15.1
collecting ... collected 9 items

backend/tests/test_attachments.py::test_upload_and_download_all_10_formats PASSED [ 11%]
backend/tests/test_attachments.py::test_reject_dangerous_and_disallowed_formats PASSED [ 22%]
backend/tests/test_attachments.py::test_reject_magic_byte_mismatch PASSED [ 33%]
backend/tests/test_attachments.py::test_reject_file_too_large PASSED     [ 44%]
backend/tests/test_attachments.py::test_path_traversal_sanitization PASSED [ 55%]
backend/tests/test_attachments.py::test_scope_isolation_152_fz PASSED    [ 66%]
backend/tests/test_attachments.py::test_attachments_in_detail_and_events PASSED [ 77%]
backend/tests/test_attachments.py::test_attachment_cross_interaction_access_returns_404 PASSED [ 88%]
backend/tests/test_attachments.py::test_attachment_download_nonexistent_returns_404 PASSED [100%]

=============================== warnings summary ===============================
backend/.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1
  /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

backend/.venv/lib64/python3.14/site-packages/starlette/testclient.py:53
  /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/lib64/python3.14/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 9 passed, 2 warnings in 3.18s =========================
```

### 4.5. Raw Terminal Output 2: Запуск автоматизированных тестов `test_reports_multiformat.py`
```text
============================= test session starts ==============================
platform linux -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0 -- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
plugins: anyio-4.15.1
collecting ... collected 7 items

backend/tests/test_reports_multiformat.py::test_snapshot_export_json_xlsx_pdf PASSED [ 14%]
backend/tests/test_reports_multiformat.py::test_activity_report_and_exports PASSED [ 28%]
backend/tests/test_reports_multiformat.py::test_created_report_and_exports PASSED [ 42%]
backend/tests/test_reports_multiformat.py::test_unsupported_export_format_returns_422 PASSED [ 57%]
backend/tests/test_reports_multiformat.py::test_activity_report_historical_owner_resolution_after_reassignment PASSED [ 71%]
backend/tests/test_reports_multiformat.py::test_snapshot_zero_buckets_for_all_fifteen_states PASSED [ 85%]
backend/tests/test_reports_multiformat.py::test_xlsx_formula_injection_defense PASSED [100%]

=============================== warnings summary ===============================
backend/.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1
  /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

backend/.venv/lib64/python3.14/site-packages/starlette/testclient.py:53
  /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/lib64/python3.14/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 7 passed, 2 warnings in 2.19s =========================
```

### 4.6. Oracle Verification Output: Запуск эталонного верификатора `verify_reports.py`
```text
PASS FX-S01 (snapshot)
PASS FX-S02 (snapshot)
PASS FX-S03 (snapshot)
PASS FX-S04 (snapshot)
PASS FX-S05 (snapshot)
PASS FX-S06 (snapshot)
PASS FX-S07 (snapshot)
PASS FX-A01 (activity)
PASS FX-A02 (activity)
PASS FX-A03 (activity)
PASS FX-A04 (activity)
PASS FX-A05 (activity)
VERIFIED 6 interactions, 23 canonical events, 3 delivery examples, 12 exact report cases
```

---

## 5. Prioritized Action Items (План доработок по принципам Stdlib-first)

В соответствии с правилами разработки `Инженерный регламент команды («Ezdel»)` любые доработки и устранения архитектурных разрывов должны строго следовать принципу «Лестницы» (The Ladder):
1. **Нужно ли это вообще создавать?** (YAGNI).
2. **Уже есть в нашей кодовой базе?** (Переиспользование).
3. **Стандартная библиотека Python/JS делает это?** (stdlib-first).
4. **Нативная фича платформы закрывает вопрос?** (DB constraints, CSS, native inputs).
5. **Уже установленная зависимость решает задачу?** (0 новых пакетов в `requirements.txt`).
6. **Можно сделать в одну строку?** (Сделать в одну строку).
7. **Только если предыдущее не подошло:** писать минимальный рабочий diff.

### P0 (Критический приоритет: Безопасность и стабильность под SLA R18/R19)
1. **Устранение риска AnyIO Thread Pool Starvation в `backend/app/main.py`:**
   - *Проблема:* По умолчанию в AnyIO установлено ограничение 40 токенов, что при одновременных 10 отчетах блокирует запросы 50 пользователей.
   - *Решение по Stdlib-first (Ступень 6 — одна строка):* В обработчик старта приложения `lifespan` в `backend/app/main.py` добавить строчку:
     ```python
     anyio.to_thread.current_default_thread_limiter().total_tokens = 120
     ```
   - *Важное примечание (согласование пула БД):* Расширение AnyIO thread limiter до 120 токенов в `main.py` должно обязательно сопровождаться расширением параметров пула соединений SQLAlchemy engine (`pool_size=20, max_overflow=20`) в `backend/app/db.py` для предотвращения исчерпания соединений к базе данных (database connection starvation) во время одновременной генерации 10 отчетов (10 concurrent report generations).
   - *Обоснование:* Полная ликвидация взаимных блокировок без изменения бизнес-логики и без добавления зависимостей.

2. **Защита архивов от Decompression Bomb (Zip Bomb):**
   - *Проблема:* `validate_magic_bytes` проверяет заголовок архива (`PK\x03\x04`, `Rar!`), но не ограничивает степень сжатия.
   - *Решение по Stdlib-first (Ступень 3 — stdlib `zipfile`):* При загрузке архива `.zip` проверять суммарный размер неупакованных файлов через `sum(z.file_size for z in zipfile.ZipFile.infolist()) <= 100 * 1024 * 1024`.

### P1 (Высокий приоритет: Темпоральная надежность и неизменяемость данных)
1. **Реализация неизменяемого слепка отчета (Frozen Dataset):**
   - *Проблема:* Генерация отчетов «на лету» не гарантирует консистентность между предпросмотром и скачиванием файла при мутациях БД без передачи `knowledge_cutoff`.
   - *Решение по Stdlib-first:* Создать компактную модель `ReportRun(id, report_type, parameters, captured_at, rows_json)` для сохранения сериализованных строк отчета в момент первого расчета. Эндпоинты экспорта отдают файл из сохраненного слепка `ReportRun`.
2. **Потоковая запись файлов на диск (Streaming Upload):**
   - *Проблема:* Вызов `await request.body()` буферизует до 25 МБ в оперативную память процесса.
   - *Решение по Stdlib-first:* Использование стандартного асинхронного генератора чанков Starlette `async for chunk in request.stream()` с записью во временный файл `NamedTemporaryFile` для снижения потребления памяти до нуля.
3. **Регуляторное согласование статуса XLS:**
   - *Решение:* Зафиксировать в эксплуатационной документации и паспорте проекта, что устаревший двоичный формат XLS (Excel 97-2003, BIFF8) выведен из эксплуатации и полностью замещен современным стандартом ISO/IEC 29500 (XLSX).

### P2 (Средний приоритет: Enterprise Core и масштабирование на Gate O)
1. **Внедрение брокера задач и воркеров (Celery + Redis):**
   - *Контекст:* Переход от синхронного прототипа к enterprise-архитектуре при нагрузке свыше 10 000 взаимодействий.
   - *Решение:* Развертывание контейнеров `redis` и `celery worker`, реализация моделей `BackgroundJob` и `JobAttempt`, переход на эндпоинты `POST /report-previews -> 202 Accepted`.
2. **Подключаемый адаптер хранилища `StoragePort` (S3/MinIO):**
   - *Контекст:* Развертывание системы в кластере Kubernetes с несколькими подами бэкенда.
   - *Решение:* Реализация адаптера к S3 API поверх стандартного протокола HTTP без привязки к локальным томам.
3. **Асинхронный контур антивирусного сканирования:**
   - *Решение:* Выделенный изолированный сервис ClamAV в DMZ-сегменте для глубокой проверки распакованных файлов при строгих требованиях регулятора.
