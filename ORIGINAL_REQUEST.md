# Original User Request

## 2026-09-19T17:17:17Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Multi-agent execution via teamwork_preview  
> Requested team: 4-agent engineering team (Backend Engineer, Frontend & UX Engineer, QA & Test Engineer, Architecture Reviewer & Ponytail Guardian)

Реализация пакета задач B11, B14, B15, B18 проекта «ИТ Школа Ростелекома — CRM» (`rost_crm`): добавление сущностей договоров, лицензий, контактов вузов и вложений, реализация эндпоинта `PATCH /api/v1/interactions/{id}` с CAS-блокировкой для устранения дедлока D02, отображение всех альтернативных переходов в карточке взаимодействия и стилизация под дизайн-систему Ростелеком Gen2 Light Theme.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## References
- `AGENTS.md` — обязательные правила разработки, Ponytail и инварианты безопасности (152-ФЗ, CAS, in-memory JWT).
- `docs/planning/adr/002-contract-entities-and-interaction-patch.md` — спецификация моделей и метода PATCH.
- `docs/planning/adr/001-ui-design-system-and-full-scope.md` — токены дизайн-системы Ростелеком Gen2 Light Theme.
- `docs/planning/01-technical-specification.md` — предметная модель, ролевые права и граф базового процесса.
- `docs/planning/02-development-plan.md` — задачи B11, B14, B15, B18.
- `docs/planning/03-acceptance-scenarios.md` — сценарии приёмки AC01, AC06, AC07, AC09, AC10.

---

## Requirements

### R1. Сущности предметной модели и каталоги (B11, B18, ADR 002)
- В `backend/app/models.py` реализовать новые модели:
  - `OrganizationContact`: `id`, `organization_id` (FK), `full_name` (250), `position` (200), `email` (nullable), `phone` (nullable), `active` (bool, default True).
  - `Contract`: `id`, `organization_id` (FK), `number` (100), `signed_on` (DateTime nullable), `status` (default 'active'), `created_at`.
  - `License`: `id`, `organization_id` (FK), `product_id` (FK), `contract_id` (FK nullable), `signed_on` (DateTime nullable), `term_years` (int nullable), `transfer_status` (default 'pending'), `created_at`.
  - `Attachment`: `id`, `interaction_id` (FK), `visit_id` (str, index=True), `file_name` (255), `file_path` (500), `file_size` (int), `content_type` (100), `checksum` (64, sha256), `uploaded_by` (FK users.id), `created_at`.
  - Расширить модель `Interaction` внешними ключами: `contract_id` (FK contracts.id, nullable), `license_id` (FK licenses.id, nullable), `contact_id` (FK organization_contacts.id, nullable).
- В `backend/app/services.py:catalogs()` включить сериализацию контактов, договоров и лицензий доступных организаций.
- В `backend/app/services.py:interaction_dict()` сериализовать связанные поля: `contact_id`, `contact_name`, `contract_id`, `contract_number`, `license_id`, `license_status`.
- В `backend/app/seed.py` добавить демонстрационные контакты, договоры и лицензии для тестовых организаций. Сохранить инвариант `("manager-a", "org-1"): (True, False)` и `("manager-b", "org-2"): (True, False)` (`read_all=False`).

### R2. Метод `PATCH /api/v1/interactions/{id}` и устранение дедлока D02 (B14, B15, ADR 002)
- Создать Pydantic-схему `InteractionUpdate`: `expected_revision` (int), `title` (str | None), `program_id` (str | None), `product_id` (str | None), `cycle_label` (str | None), `contract_id` (str | None), `license_id` (str | None), `contact_id` (str | None).
- Реализовать маршрут `PATCH /api/v1/interactions/{id}` с поддержкой заголовка `Idempotency-Key` (до 200 символов, через `begin_command` / `finish_command`).
- Проверять область доступа (`scope_clause(user)`): попытка обращения к чужой карточке возвращает строго `404 Not Found`.
- Выполнять атомарный CAS update по `expected_revision`. При несовпадении версий возвращать `409 Conflict`.
- При указании `program_id` и `product_id` проверять их совместимость через `validate_subject(db, program_id, product_id)`.
- Если карточка уже находится на этапе `materials_transfer` или далее, запретить сброс программы или продукта в `null`.
- Фиксировать темпоральное событие в аудит-логе: `InteractionEvent(type="attributes_corrected", sequence=last+1, payload={"changes": {...}, "snapshot": ...})`.

### R3. Дизайн-система Ростелеком Gen2 Light Theme и отображение всех переходов в UI (B15, B20, ADR 001)
- В `frontend/src/styles.css` внедрить токены темы Rostelecom Light Theme:
  - Основной: `--rtk-color-primary: #7700FF`, hover `--rtk-color-primary-hover: #6C00E0`.
  - Акцент: `--rtk-color-accent: #FF4F12`.
  - Фон: `--rtk-color-background: #F4F5F8`.
  - Карточки: `--rtk-color-card: #FFFFFF`, границы `--rtk-color-border: #E2E5EB`.
  - Текст: высококонтрастный `--rtk-color-text: #101828`, вторичный `--rtk-color-muted: #475467`.
  - Радиусы скругления: `--rtk-radius-md: 8px`, `--rtk-radius-lg: 12px`.
- В `frontend/src/views/InteractionPage.tsx` устранить выбор единственного перехода `item.allowed_transitions[0]`. Отображать все доступные переходы из массива `allowed_transitions`:
  - Кнопки прямого перехода: `variant="primary"`.
  - Кнопки возврата на доработку / циклов: `variant="secondary"`.
  - Кнопка отмены взаимодействия: `variant="danger"`.
  - Для переходов с `comment_required=true` открывать модальное окно с обязательным вводом комментария/причины.
- Реализовать форму/модальное окно «Редактировать параметры» в карточке взаимодействия:
  - Возможность выбора программы, продукта (совместимого с выбранной программой), метки цикла, контакта и договора.
  - Отправка `PATCH /api/v1/interactions/{id}` с `expected_revision` и `Idempotency-Key: crypto.randomUUID()`.
  - Реактивное обновление состояния карточки без полной перезагрузки страницы (SPA). При конфликте версий (409) выводить информативное сообщение.

### R4. Автоматизированные тесты и предотвращение регрессий (QA)
- Создать тестовый модуль `backend/tests/test_interaction_patch.py`:
  - Успешное добавление программы и продукта к карточке, созданной без них, с последующим успешным переходом в `materials_transfer` (доказательство устранения дедлока D02 / AC07).
  - Проверка CAS: отказ с кодом `409 Conflict` при передаче устаревшей `expected_revision`.
  - Отказ с кодом `422 / 400 VALIDATION_ERROR` при попытке связать несовместимые программу и продукт.
  - Проверка идемпотентности: повторный запрос с тем же `Idempotency-Key` возвращает прежний результат без дублирования событий.
  - Проверка изоляции доступа (152-ФЗ / Scope): менеджер Б получает `404 Not Found` при попытке `PATCH` чужой карточки менеджера А.
- Обеспечить прохождение 100% тестов в `backend/tests/test_working_slice.py` (включая устранение падений на переназначении карточки).

### R5. Контроль чистоты кода и соблюдение принципов Ponytail (TL)
- Использовать только стандартную библиотеку Python (`hashlib`, `uuid`, `datetime`) и нативный веб-API (`crypto.randomUUID()`).
- Не добавлять сторонних внешних библиотек в `requirements.txt` и `package.json`.
- Запустить скрипты проверки спецификации и графа процессов:
  - `python3 docs/checks/verify_workflow.py` -> PASS
  - `python3 docs/checks/verify_reports.py` -> PASS
  - `python3 docs/checks/verify_plan.py` -> PASS
- Проверить сборку фронтенда (`pnpm build`) без ошибок типов TypeScript.

---

## Acceptance Criteria

### Функциональная приёмка (AC01, AC07, AC09, AC10)
- [ ] Все новые сущности (`OrganizationContact`, `Contract`, `License`, `Attachment`) созданы в БД и имеют корректные внешние ключи.
- [ ] Каталоги `/api/v1/catalogs` возвращают контакты, договоры и лицензии для доступных организаций.
- [ ] Карточка взаимодействия сериализует `contact_id`, `contact_name`, `contract_id`, `contract_number`, `license_id`, `license_status`.
- [ ] Карточка, созданная без программы и продукта, успешно дозаполняется через `PATCH /api/v1/interactions/{id}` и беспрепятственно переходит на этап `materials_transfer` (дедлок D02 устранен).
- [ ] При несовпадении `expected_revision` метод `PATCH` отклоняет запрос со статусом `409 Conflict`.
- [ ] В интерфейсе `InteractionPage.tsx` отображаются все допустимые переходы (`allowed_transitions`), включая отмену и возврат на доработку.
- [ ] Переходы с `comment_required: true` требуют ввода комментария перед отправкой.
- [ ] Цветовая палитра интерфейса соответствует токенам Rostelecom Light Theme (`#7700FF`, `#FF4F12`, `#F4F5F8`, `#101828`).

### Безопасность и целостность (AC05, AC06, 152-ФЗ)
- [ ] Менеджер при обращении к чужой карточке через `PATCH` получает `404 Not Found`.
- [ ] Переназначение карточки руководителем новому менеджеру немедленно закрывает доступ для старого менеджера.
- [ ] Токены аутентификации хранятся только in-memory (отсутствуют в `localStorage`).

### Автоматизированная верификация
- [ ] Все тесты `backend/tests/test_working_slice.py` и `backend/tests/test_interaction_patch.py` завершаются со статусом PASS (`100% OK`).
- [ ] Сборка фронтенда `pnpm build` завершается без ошибок.
- [ ] Скрипты `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` выдают `PASS`.

## 2026-09-19T18:49:03Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Multi-agent execution via teamwork_preview  
> Requested team: 4-agent engineering team (Backend Lead Architect, Frontend & UX Lead, QA & Forensic Test Engineer, Architecture Reviewer & Ponytail Guardian)

Реализация пакета Enterprise Core & Analytics Engine (задачи B18.2, B22, B24, B25, B12/B13, B16) проекта «ИТ Школа Ростелекома — CRM» (`rost_crm`): безопасное изолированное файловое хранилище 10 форматов ТЗ с валидацией magic bytes, аналитический движок трёх типов отчётов (snapshot, activity, created) с бинарной выгрузкой в XLSX, векторный PDF и JSON, двухфазный мастер импорта каталогов (preview/commit), интерактивный граф жизненного цикла карточки и SVG/Canvas диаграммы воронки в палитре Rostelecom Gen2 Light Theme.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## References
- `AGENTS.md` — стандарты Ponytail Ladder (stdlib-first, 0 стороннего оверинжиниринга), инварианты безопасности (152-ФЗ, ФСТЭК №117, CAS revision, in-memory JWT).
- `docs/planning/adr/001-ui-design-system-and-full-scope.md` — дизайн-система Ростелеком Gen2 Light Theme.
- `docs/planning/adr/002-contract-entities-and-interaction-patch.md` — модели данных и метод PATCH.
- `docs/planning/01-technical-specification.md` — спецификация отчётов, файлов и процессов.
- `docs/planning/04-base-workflow.json` — эталонный граф 13 рабочих и 2 терминальных состояний.
- `docs/planning/05-report-fixture.json` — эталонные данные и результаты отчётов snapshot и activity.

---

## Requirements

### R1. Безопасное файловое хранилище и контроллеры вложений (B18.2, B19)
- Создать изолированный сервис хранения в `backend/app/files.py`:
  - Каталог хранения: `storage/attachments/{interaction_id}/` (вне публичного веб-корня).
  - Поддержка ровно **10 форматов ТЗ**: `png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx`.
  - Валидация фактического содержимого по сигнатурам заголовков (magic bytes) и MIME-типам. Отклонение недопустимых форматов (exe, sh, bat, php и др.) со статусом `422 FILE_TYPE_NOT_ALLOWED`.
  - Строгий лимит размера файла: до **25 МБ** (при превышении — `413 FILE_TOO_LARGE`).
  - Санитизация имён файлов (защита от Path Traversal `../`, спецсимволов), генерация UUID на диске, сохранение оригинального имени в БД.
  - Расчёт контрольной суммы $SHA\text{-}256$ и запись в `Attachment.checksum`.
- Эндпоинты в `backend/app/main.py`:
  - `POST /api/v1/interactions/{id}/attachments` (`multipart/form-data`, проверка `scope_clause`, запись в БД, темпоральное событие `attachment_uploaded`).
  - `GET /api/v1/interactions/{id}/attachments` (список метаданных файлов карточки).
  - `GET /api/v1/interactions/{id}/attachments/{attachment_id}/download` (авторизованная потоковая отдача `FileResponse` с заголовком `Content-Disposition`, проверка прав на карточку: чужой ID -> `404 Not Found`).

### R2. Аналитический движок и бинарный экспорт XLSX / PDF / JSON (B22, B24)
- В `backend/app/services.py` и `backend/app/reports_export.py` реализовать расчёт 3 режимов отчётов:
  - `snapshot`: срез состояния на дату `as_of` с учётом `knowledge_cutoff` и текущих прав пользователя.
  - `activity`: переходы за интервал `[from_date, to_date)` с определением исторического ответственного на момент перехода (`owner_at_event`) по эталону `05-report-fixture.json`.
  - `created`: взаимодействия, созданные за интервал `[from_date, to_date)`.
- Генератор **XLSX-файлов** (`reports_export.py`):
  - Полноценная генерация Office Open XML (`.xlsx`) через стандартный модуль `zipfile` и XML-шаблонизацию или минимальный генератор без тяжёлых зависимостей.
  - Оформление Ростелекома: шапка `#7700FF` с белым текстом, чередующиеся строки `#F4F5F8`, рамки, автоподбор ширины колонок, лист метаданных (дата генерации, инициатор, фильтры, `knowledge_cutoff`).
- Генератор многостраничных **PDF-файлов** (`reports_export.py`):
  - Векторный чистый PDF с таблицей отчёта, фирменным колонтитулом ПАО «Ростелеком», сквозной нумерацией («Стр. X из Y»), параметрами фильтрации и грифом конфиденциальности.
- Эндпоинты в `backend/app/main.py`:
  - `POST /api/v1/reports/snapshot/export` (поддержка `format=json|xlsx|pdf`).
  - `POST /api/v1/reports/activity` и `POST /api/v1/reports/activity/export`.
  - `POST /api/v1/reports/created` и `POST /api/v1/reports/created/export`.

### R3. Двухфазный мастер импорта каталогов (B12, B13)
- В `backend/app/importer.py`:
  - Парсинг табличных файлов (XLSX, XLS, CSV) с автоматическим распознаванием колонок: Название вуза, Тип, Ответственный от вуза, Контакты, Программа, Продукт.
  - `POST /api/v1/imports/organizations/preview`: dry-run парсинг без записи в БД, валидация полей, отчёт (`rows_total`, `valid_count`, `error_count`, `preview_rows`, `errors`).
  - `POST /api/v1/imports/organizations/commit`: транзакционное создание организаций, контактов и связей с защитой от дублей через `Idempotency-Key`.

### R4. Интерфейс аналитики, вложений, мастера импорта и графа процессов (FE / B15, B20, B25)
- **Вложения в карточке (`InteractionPage.tsx`):**
  - Секция «Вложения и документы»: список файлов с бейджами форматов (PDF, DOC, XLS, IMG, ARCHIVE), метаданными (размер, автор, дата), кнопкой авторизованного скачивания.
  - Форма загрузки (drag-and-drop, валидация размера до 25 МБ на клиенте до отправки, индикатор прогресса).
- **Аналитика и экспорт (`Reports.tsx`):**
  - Переключение 3 режимов: «Срез на дату (Snapshot)», «Динамика переходов (Activity)», «Созданные карточки (Created)».
  - Панель скачивания: отдельные кнопки **Скачать XLSX**, **Скачать PDF**, **Скачать JSON**.
  - Интерактивная SVG/Canvas диаграмма распределения карточек по этапам в цветах темы Rostelecom Gen2 (`#7700FF`, `#FF4F12`).
- **Мастер импорта (`ReferenceViews.tsx`):**
  - Модальный 3-шаговый мастер: Загрузка файла -> Предпросмотр валидации и ошибок -> Подтверждение импорта с прогресс-баром.
- **Интерактивный граф процесса (`WorkflowGraphView.tsx`):**
  - Визуализация 13 рабочих и 2 терминальных состояний воронки с подсветкой текущего положения карточки.

### R5. Комплексное тестирование и контроль качества (QA & TL)
- Новые тестовые модули в `backend/tests/`:
  - `test_attachments.py`: загрузка 10 форматов, отказ 422 на недопустимые типы, лимит 25 МБ (413), path traversal, SHA-256, 152-ФЗ (404 на чужой файл).
  - `test_reports_multiformat.py`: проверка сигнатур XLSX (`PK\x03\x04`), PDF (`%PDF-`), сверка данных с `05-report-fixture.json`.
  - `test_import_wizard.py`: dry-run превью без мутаций, идемпотентный коммит, обработка ошибок строк.
- Регрессия: 100% PASS для всех существующих 27 тестов (общее число тестов > 40).
- Верификация спецификаций: `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` -> PASS.
- Соблюдение Ponytail: отсутствие раздутых runtime-библиотек, строгие серверные проверки прав.

---

## Acceptance Criteria

### Файловая подсистема (AC10, 152-ФЗ)
- [ ] Загрузка и потоковое скачивание файлов всех 10 форматов ТЗ работают корректно.
- [ ] Недопустимые форматы файлов (exe, sh, php и т.д.) отклоняются сервером с кодом 422.
- [ ] Файлы размером свыше 25 МБ отклоняются сервером с кодом 413.
- [ ] Менеджер при попытке скачать файл из чужой карточки получает строго 404 Not Found.
- [ ] Имена файлов на диске изолированы через UUID, в БД хранится вычисленный SHA-256.

### Аналитика и отчёты (AC11, AC13, AC14, AC16, AC17)
- [ ] Доступны три типа отчётов: snapshot, activity, created.
- [ ] Экспорт отчётов выдаёт валидный бинарный XLSX с сигнатурой `PK\x03\x04` и стилизацией Ростелекома.
- [ ] Экспорт отчётов выдаёт валидный векторный многостраничный PDF с сигнатурой `%PDF-` и нумерацией страниц.
- [ ] Экспорт в JSON сохраняет полную структурную совместимость.
- [ ] В UI отображается интерактивная диаграмма распределения в цветах Gen2.

### Мастер импорта (AC02, AC03)
- [ ] Эндпоинт preview выполняет сухой прогон без внесения изменений в БД.
- [ ] Эндпоинт commit применяет данные транзакционно с защитой от дублирования по Idempotency-Key.
- [ ] Ошибочные строки снабжаются понятными диагностическими сообщениями.

### Интерфейс и граф процессов (AC07, AC09, R28)
- [ ] В карточке взаимодействия отображаются прикреплённые файлы и drag-and-drop загрузчик.
- [ ] Граф процесса наглядно отображает 13 рабочих и 2 терминальных статуса с текущей позицией.
- [ ] Токены Rostelecom Gen2 Light Theme применены ко всем новым компонентам без перезагрузки страницы (SPA).

### Автоматизированная верификация
- [ ] Общее количество тестов бэкенда > 40, все тесты завершаются со статусом PASS (`100% OK`).
- [ ] Скрипты `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` завершаются со статусом PASS.

## 2026-09-19T21:49:49Z

Реализация отказоустойчивого контура интеграций (задачи B26, B27, B28, B29, требования R09, R11, R12, R13, R20, сценарии AC12, AC13, AC29) проекта «ИТ Школа Ростелекома — CRM» (rost_crm): подключаемые адаптеры-заглушки (Pluggable Mock/Stub Adapters) для LMS Zion (rtkb.zion-lms.ru) и сайта на Laravel, нормализованный конверт ТЗ 7.2 v1.0, транзакционная очередь сверки (Reconciliation Inbox) с защитой от дублирования по композитному ключу, витрина учебных метрик востребованности программ и экран управления интеграциями в дизайн-системе Rostelecom Gen2 Light Theme.

Requested team: 3-agent engineering team (Backend Adapter & Schema Architect, Sync & Reconciliation Engine Engineer, Frontend UI & QA Forensic Engineer)

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## References
- AGENTS.md — стандарты Ponytail Ladder (stdlib-first, 0 новых pip/npm зависимостей), инварианты безопасности (152-ФЗ, ФСТЭК №117, in-memory JWT, CAS-ревизии, Idempotency-Key).
- docs/planning/01-technical-specification.md — раздел 7.2 «Внешние источники», структура нормализованного конверта DTO v1.0.
- docs/planning/02-development-plan.md — задачи B26, B27, B28, B29.
- docs/planning/03-acceptance-scenarios.md — сценарии AC12, AC13, AC29.
- docs/planning/adr/001-ui-design-system-and-full-scope.md — цветовая палитра темы Rostelecom Gen2 Light.

---

## Requirements

### R1. Модели данных и нормализованный конверт ТЗ 7.2 (B26, R09, R11, R12)
- В backend/app/models.py:
  - Создать модель IntegrationInbox:
    - Поля: id (String UUID), source (lms | website), entity_type (learning_metric | application), external_id (String), source_revision (String), payload (JSON / dict), status (pending, processed, quarantined, rejected), error_message (Text nullable), matched_organization_id (FK nullable), matched_interaction_id (FK nullable), received_at (DateTime), processed_at (DateTime nullable).
    - Уникальное ограничение / индекс: (source, entity_type, external_id, source_revision) для строгой дедупликации на уровне БД.
  - Создать модель LearningMetric:
    - Поля: id (String UUID), organization_id (FK к Organization), program_id (FK к Program), metric_code (String: active_cohorts, students_enrolled, students_completed, attendance_rate), value (Float), unit (String), as_of (DateTime), source (String), external_id (String), created_at (DateTime).
- Конверт нормализованных данных DTO v1.0 (в backend/app/integrations/base.py):
  - Поля: schema_version ("1.0"), source, entity_type, external_id, source_revision, operation ("upsert"), effective_at, received_at, payload.

### R2. Подключаемые адаптеры-заглушки (Pluggable Mock/Stub Adapters) (B27, B28, R13, R20)
- В модуле backend/app/integrations/:
  - base.py: интерфейс BaseIntegrationAdapter с абстрактными методами:
    - fetch_updates(since: datetime | None = None) -> list[NormalizedEnvelope]
    - health_check() -> dict[str, Any]
  - mock_lms.py: MockLMSAdapter — эмулирует боевую LMS Zion (https://rtkb.zion-lms.ru/):
    - Реалистичные фикстуры образовательных потоков, курсов и метрик студентов по вузам (org-1, org-2, org-3) и программам (program-devops, program-web).
    - Генерация записей метрик active_cohorts, students_enrolled, students_completed.
  - mock_website.py: MockWebsiteAdapter — эмулирует заявки с сайта на Laravel:
    - Поступление заявок от вузов на вступление в ИТ-Школу (название вуза, контакты представителя, email, телефон, желаемая программа, комментарий).
    - Генерация как известных вузов, так и новых/неизвестных организаций, требующих ручной сверки.
  - factory.py: фабрика get_adapter(source: str) -> BaseIntegrationAdapter с возможностью переключения режима работы (mock / live) через настройки в config.py без изменения клиентского кода.

### R3. Движок синхронизации и очередь сверки (Reconciliation Inbox) (B26, B28, AC12, AC13)
- В backend/app/integrations/service.py:
  - sync_source(db, user, source):
    - Опрос соответствующего адаптера через fetch_updates().
    - Сохранение пакетов в IntegrationInbox с пропуском дубликатов по ключу (source, entity_type, external_id, source_revision).
    - Автоматическая обработка метрик: сохранение в LearningMetric.
    - Обработка заявок с сайта:
      - Если организация однозначно сопоставлена -> предложение привязки / автосоздание.
      - Если организация неизвестна или найдено несколько совпадений -> перевод в статус pending в очереди сверки.
  - reconcile_application(db, user, inbox_id, action, params, idempotency_key):
    - Доступные действия: link_existing (привязать к существующей организации), create_new (создать новую организацию и контакт), reject (отклонить как невалидную/дубликат).
    - При успешной сверке: опциональное создание карточки взаимодействия (Interaction) с назначением ответственного в рамках scope пользователя.
    - Защита от гонок и повторов через Idempotency-Key.
  - get_learning_metrics_summary(db, user, ...):
    - Агрегация показателей востребованности (число потоков, охват студентов по направлениям) с фильтрацией по организации и программе.

### R4. REST API шлюза интеграций (B26, B29)
- В backend/app/main.py:
  - GET /api/v1/integrations/status: текущий статус адаптеров (LMS Zion, Сайт Laravel), режим работы (mock/stub/live), время последней синхронизации, счетчики (всего, в очереди pending, обработано processed, ошибок).
  - POST /api/v1/integrations/sync/{source}: триггер ручной синхронизации источника (lms или website).
  - GET /api/v1/integrations/inbox: получение списка записей очереди сверки с пагинацией и фильтрами (source, status).
  - POST /api/v1/integrations/inbox/{id}/resolve: разрешение коллизии оператором с заголовком Idempotency-Key.
  - GET /api/v1/integrations/metrics: витрина метрик учебной востребованности с агрегированными суммами.

### R5. Пользовательский интерфейс Rostelecom Gen2 (B29, AC29)
- В frontend/src/views/IntegrationsView.tsx экран «Шлюз интеграций и сверка»:
  - Статус внешних систем: плашки LMS Zion и Сайта Laravel с отображением режима («Эмуляция контракта»), даты последней синхронизации и кнопкой «Синхронизировать сейчас».
  - Очередь сверки (Reconciliation Inbox): таблица входящих заявок со статусами (pending — требует внимания, processed — сопоставлено, rejected — отклонено).
  - Модальное окно сопоставления заявки: выбор действия (привязать к существующему вузу из справочника или создать новый вуз), выбор ответственного менеджера, кнопка «Подтвердить и создать взаимодействие».
  - Витрина показателей востребованности: сводные карточки и графики охвата студентов, активных потоков и процента завершения по программам.
- Интеграция пункта меню «Интеграции» в навигацию приложения (App.tsx) для ролей руководителя (supervisor) и администратора (admin).

### R6. Комплексное тестирование и контроль качества (QA)
- Создать тестовый модуль backend/tests/test_integrations.py:
  - Проверка забора данных из MockLMSAdapter и сохранения в LearningMetric.
  - Проверка строгой идемпотентности и дедупликации: повторный запуск синхронизации не создаёт дубликатов в IntegrationInbox и LearningMetric.
  - Поступление заявки от неизвестного вуза: статус pending в очереди сверки.
  - Разрешение заявки оператором (resolve): создание организации/контакта/взаимодействия с защитой Idempotency-Key.
  - Проверка 152-ФЗ изоляции: менеджер не имеет доступа к управлению глобальными интеграциями; доступ разрешён руководителю и администратору.
- Регрессия: 100% PASS для всех существующих 48 тестов (общее число тестов > 55).
- Верификация спецификаций: verify_workflow.py, verify_reports.py, verify_plan.py -> PASS.
- Соблюдение Ponytail Ladder: 0 сторонних пакетов в requirements.txt и package.json.

---

## Acceptance Criteria

### Контур адаптеров и конверт ТЗ 7.2 (AC12, R09, R11)
- [ ] Все пакеты данных приводятся к единому формату DTO v1.0 со всеми обязательными полями.
- [ ] MockLMSAdapter эмулирует контракты образовательных метрик Zion LMS без внешних сетевых вызовов.
- [ ] MockWebsiteAdapter эмулирует поток заявок на вступление в ИТ-Школу от вузов.
- [ ] Фабрика адаптеров поддерживает переключение режимов без изменения кода сервисов.

### Очередь сверки и дедупликация (AC13, R12, R13, R20)
- [ ] Повторные пакеты с тем же композитным ключом (source, entity_type, external_id, source_revision) дедуплицируются без создания дублирующих записей.
- [ ] Заявки от неизвестных вузов переводятся в статус pending в очереди сверки.
- [ ] Оператор может разрешить заявку (привязать к существующей организации или создать новую) с созданием карточки взаимодействия.
- [ ] Операция разрешения заявки защищена заголовком Idempotency-Key.

### Пользовательский интерфейс и витрина метрик (AC29)
- [ ] В UI отображаются плашки статуса внешних систем с возможностью ручного запуска синхронизации.
- [ ] В UI представлена таблица очереди сверки с удобным модальным окном разрешения заявок.
- [ ] В UI отображается витрина учебных метрик востребованности программ.
- [ ] Пункт меню «Интеграции» доступен для ролей supervisor и admin и оформлен в палитре Rostelecom Gen2 Light.

### Автоматизированное тестирование
- [ ] Добавлены автоматические тесты в backend/tests/test_integrations.py.
- [ ] Общее количество тестов бэкенда > 55, все тесты завершаются со статусом PASS (100% OK).
- [ ] Контрольные скрипты verify_workflow.py, verify_reports.py, verify_plan.py завершаются со статусом PASS.
- [ ] В requirements.txt и package.json не добавлено ни одной новой внешней зависимости.


## 2026-09-20T07:50:28Z

# Gate P / Gate O Readiness Sprint — B17, B31, B33, B34, B36

Реализация финального спринта конкурсной готовности проекта «ИТ Школа Ростелекома — CRM» (rost_crm): мигратор процессов между версиями workflow с атомарным коммитом и аудитом, нагрузочный бенчмарк на 50 параллельных пользователей, интерактивная ролевая база знаний в UI, матрица соответствия 152-ФЗ и архитектурная документация ArchiMate 3.1 / C4.

Requested team: 3-agent engineering team (Архитектор процессов и производительности, Инженер UX и базы знаний, Специалист ИБ и архитектуры)

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## References
- AGENTS.md — стандарты Ponytail Ladder (stdlib-first, 0 новых pip/npm зависимостей), инварианты безопасности (152-ФЗ, ФСТЭК №117, in-memory JWT, CAS-ревизии, Idempotency-Key).
- docs/planning/01-technical-specification.md — раздел 4 «Жизненный цикл», раздел 5 «Права и роли».
- docs/planning/02-development-plan.md — задачи B17, B31, B33, B34, B36, требования R06, R18, R19, R21, R26, R27.
- docs/planning/03-acceptance-scenarios.md — сценарии AC06, AC18, AC19, AC21, AC26, AC27.
- docs/planning/adr/001-ui-design-system-and-full-scope.md — цветовая палитра темы Rostelecom Gen2 Light.
- 04-base-workflow.json — эталонные 13 рабочих + 2 терминальных состояния.

## Verification Resources
- Существующие 99 тестов: `cd backend && .venv/bin/python -m pytest tests/ -v`
- Оракулы спецификации: `python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py`
- Нулевой прирост зависимостей: `git diff backend/requirements.txt frontend/package.json` должен быть пустым.

---

## Requirements

### R1. Мигратор процессов между версиями workflow (Задача B17, R06)
- В `backend/app/workflow.py` и/или `backend/app/services.py`:
  - Версионирование workflow (версия 1 — базовые 15 стадий, версия 2 — расширенный шаблон с оптимизированными переходами).
  - Функция `preview_workflow_migration(db, user, from_version, to_version, status_mapping)`:
    * Проверка допустимости сопоставления (терминальные `completed`/`cancelled` не могут мапиться в рабочие).
    * Вычисление списка затронутых активных карточек (`state != terminal`, `workflow_version == from_version`).
    * Возврат отчёта: количество карточек, распределение по старым и новым статусам, коллизии.
  - Функция `commit_workflow_migration(db, user, from_version, to_version, status_mapping, idempotency_key)`:
    * Атомарный транзакционный перевод карточек на новую версию с обновлением ревизии (CAS).
    * Аудиторское событие `workflow_migrated` в `InteractionEvent` для каждой карточки (сохранение истории, комментариев, вложений).
    * Защита через `Idempotency-Key`.
- В `backend/app/main.py`:
  - `POST /api/v1/workflow/migrate/preview` (dry-run).
  - `POST /api/v1/workflow/migrate/commit` (транзакционный коммит, доступ только для `admin`/`supervisor`).

### R2. Нагрузочный бенчмарк (Задача B31, R18, R19)
- Автономный скрипт `backend/benchmarks/benchmark_load.py` на базе `asyncio` и `httpx`:
  - Эмуляция 50 параллельных пользователей (40 менеджеров, 8 руководителей, 2 администратора).
  - 10 одновременных тяжёлых аналитических отчётов (Snapshot, Activity, Created) на фоне активных запросов реестра и карточек.
  - Метрики: среднее, min, max, медиана, p95, p99, error rate.
  - Структурированный протокол `docs/benchmarks/load-test-report.md`, подтверждающий R18 (≤ 1 с) под нагрузкой R19.

### R3. Интерактивная ролевая база знаний (Задача B34, R21)
- Переработать `frontend/src/views/ReferenceViews.tsx:HelpPage` в центр базы знаний:
  - **Вкладки по ролям:**
    * **Менеджер:** реестр, карточка, 15 этапов воронки, комментарии, загрузка файлов 10 форматов.
    * **Руководитель:** распределение вузов, смена ответственного, мониторинг воронки, XLSX/PDF отчёты.
    * **Администратор:** двухфазный импорт из Excel, шлюз интеграций, очередь сверки, миграции процессов.
  - **Пошаговые сценарии:** визуальные карточки с иконками, акцентами Gen2, плашками «Важно / Внимание».
  - **Справочник кодов ошибок:** аккордеон с CAS-конфликтами, ошибками маппинга, лимитами 25 МБ, карантином.

### R4. Интерфейс мигратора в UI (Задача B17, фронтенд)
- Модальное окно «Миграция активных процессов» в `WorkflowGraphView.tsx` или `CatalogPage.tsx`:
  - Шаг 1: Выбор целевой версии и матрица сопоставления статусов.
  - Шаг 2: Предпросмотр затронутых карточек с предупреждением о необратимости.
  - Шаг 3: Подтверждение и отображение результата без перезагрузки (SPA).

### R5. Матрица соответствия 152-ФЗ (Задача B33, R27)
- Документ `docs/security/152-fz-compliance-matrix.md`:
  - Трассировка 152-ФЗ, 149-ФЗ, Приказа ФСТЭК №117 на механизмы в коде:
    * HTTP 404 на чужие ID (сокрытие факта существования).
    * In-memory JWT (защита от XSS через localStorage).
    * Magic-bytes проверка файлов, Path Traversal защита, блокировка исполняемых форматов.
    * Неизменяемый аудит `InteractionEvent`.
    * Регламент обезличивания данных при архивации.

### R6. Архитектурная модель ArchiMate 3.1 / C4 (Задача B36, R26)
- `docs/architecture/rost_crm_architecture.archimate` — ArchiMate 3.1 модель.
- `docs/architecture/c4-architecture.md` с Mermaid-диаграммами:
  - C4 Level 1: System Context (CRM, Keycloak, Users, LMS Zion, Laravel Site).
  - C4 Level 2: Containers (React SPA, FastAPI Backend, PostgreSQL, File Storage).
  - C4 Level 3: Components (Auth, Workflow, Importer, Files, Reports Export, Integrations Adapter Engine).

### R7. Тесты мигратора и регрессия (DoD)
- `backend/tests/test_workflow_migration.py`:
  - Тест корректного предпросмотра и переноса карточек.
  - Тест запрета недопустимого сопоставления (терминальный → рабочий).
  - Тест сохранения истории и вложений после миграции.
  - Тест Idempotency-Key от повторного применения.
- Полный прогон: все 99 существующих + новые тесты проходят 100%.
- Оракулы спецификации: `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` — все PASS.

---

## Acceptance Criteria

### Функциональность мигратора (B17)
- [ ] `POST /api/v1/workflow/migrate/preview` возвращает корректный отчёт с количеством затронутых карточек и распределением по статусам.
- [ ] `POST /api/v1/workflow/migrate/commit` атомарно переводит карточки с записью `workflow_migrated` в аудит-лог.
- [ ] Сопоставление терминального статуса в рабочий отклоняется с HTTP 422.
- [ ] Повторный вызов с тем же `Idempotency-Key` возвращает кэшированный ответ без повторного применения.

### Производительность (B31)
- [ ] `benchmark_load.py` запускается автономно и генерирует структурированный отчёт.
- [ ] Отчёт подтверждает p95 отклика ≤ 1 с при 50 параллельных пользователях и 10 одновременных отчётах.

### База знаний (B34)
- [ ] HelpPage содержит вкладки Менеджер / Руководитель / Администратор с релевантным контентом.
- [ ] Пошаговые сценарии визуально оформлены в палитре Gen2 (#7700FF, #FF4F12, #F4F5F8).
- [ ] Справочник ошибок реализован как аккордеон.

### Интерфейс миграции (B17 UI)
- [ ] Модальное окно миграции доступно из раздела администратора.
- [ ] Трёхшаговый wizard: выбор → предпросмотр → подтверждение, без перезагрузки страницы.

### Документация ИБ и архитектуры (B33, B36)
- [ ] `docs/security/152-fz-compliance-matrix.md` содержит трассировку требований с ссылками на код.
- [ ] `docs/architecture/c4-architecture.md` содержит Mermaid-диаграммы L1, L2, L3.
- [ ] `docs/architecture/rost_crm_architecture.archimate` — валидный XML.

### Регрессия и качество
- [ ] `pytest tests/ -v` — 100% pass rate (99 существующих + новые тесты мигратора).
- [ ] `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` — все PASS.
- [ ] Нулевой прирост зависимостей: `git diff backend/requirements.txt frontend/package.json` пуст.

## Follow-up — 2026-09-20T17:14:24Z

# Infrastructure & Supply Chain Security Audit Sprint (DevSecOps)

Комплексный аудит и доведение до производственного идеала инфраструктуры проекта «ИТ Школа Ростелекома — CRM» (rost_crm) и безопасности всех используемых библиотек (Часть 1 генерального аудита перед защитой).

Requested team: 3-agent engineering team (DevSecOps & Архитектура контейнеризации, Инженер по безопасности библиотек и зависимостей, Инженер автоматизации инфраструктуры)

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## References
- docs/planning/01-technical-specification.md — раздел 7 «Инфраструктура и эксплуатация» (требования к размеру вложений 25 МБ, Docker, Nginx, персистентность).
- docs/planning/02-development-plan.md — задачи B05, B32, B33, требования R19, R24–R27.
- AGENTS.md — стандарты Ponytail Ladder (минимальный объем зависимостей, чистый stdlib), инварианты безопасности (152-ФЗ, ФСТЭК №117, non-root контейнеры).

## Verification Resources
- Существующие 128 тестов: `cd backend && .venv/bin/python -m pytest tests/ -v`
- Оракулы спецификации: `python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py`
- Новый инфраструктурный оракул: `python3 docs/checks/verify_infra.py`
- Проверка зависимостей: `git diff backend/requirements.txt frontend/package.json`

---

## Requirements

### R1. Усиление безопасности Nginx и контейнеров Docker (DevSecOps)
- **Конфигурация Nginx (`deploy/nginx.conf`)**:
  - Устранить расхождение лимитов размера тела запроса: изменить `client_max_body_size` с `2m` на `25m` для полного соответствия нормативу ТЗ (вложения до 25 МБ).
  - Добавить заголовки усиления безопасности (Hardening Headers):
    * `X-Frame-Options: SAMEORIGIN` (защита от Clickjacking).
    * `X-Content-Type-Options: nosniff` (защита от MIME-sniffing).
    * `Content-Security-Policy` с безопасными директивами (default-src 'self', script-src 'self' 'unsafe-inline', style-src 'self' 'unsafe-inline', img-src 'self' data: blob:, connect-src 'self' http: ws:).
    * `Permissions-Policy: geolocation=(), camera=(), microphone=()`.
- **Dockerfile бэкенда (`backend/Dockerfile`)**:
  - Обеспечить создание рабочего каталога `/app/storage` до переключения на непривилегированного пользователя с корректными правами (`mkdir -p /app/storage && chown -R appuser:appuser /app/storage`).
  - Гарантировать работу контейнера строго под `USER appuser` (uid 10001).
- **Dockerfile фронтенда (`frontend/Dockerfile`)**:
  - Проверить многоэтапную сборку на `node:24-alpine` и запуск на `nginx:1.28-alpine` под `USER nginx`.
- **Отказоустойчивость и персистентность (`compose.yaml`)**:
  - Добавить именованный том `storage-data` в секцию `volumes:`, подключить его к сервису `api` (`storage-data:/app/storage`).
  - Проверить корректность цепочки `depends_on` с `condition: service_healthy` (api зависит от postgres и keycloak, frontend зависит от api).
  - Проверить таймауты и интервалы в блоках `healthcheck`.

### R2. Аудит безопасности цепочки поставок библиотек (Supply Chain Security)
- **Python зависимости (`backend/requirements.txt`, `backend/requirements-dev.txt`)**:
  - Провести аудит всех пакетов (`fastapi`, `uvicorn`, `SQLAlchemy`, `psycopg`, `PyJWT`, `pydantic`, `pytest`, `httpx`) на отсутствие известных уязвимостей (CVE) по базам Safety / PyPI / OSV.
  - Подтвердить соблюдение принципа Ponytail: строгий минимум зависимостей (6 prod-пакетов), генерация отчетов и экспорт XLS/PDF на чистом Python stdlib (`zipfile`, `xml.etree.ElementTree`).
- **Node.js зависимости (`frontend/package.json`, `frontend/pnpm-lock.yaml`)**:
  - Провести аудит зависимостей фронтенда (`react`, `react-dom`, `keycloak-js`, `vite`, `typescript`).
  - Подтвердить отсутствие критических уязвимостей в lock-файле.
- **Отчет безопасности зависимостей**:
  - Сформировать подробный документ `docs/security/dependency-security-audit.md` с реестром библиотек, версий, лицензий (MIT/BSD/Apache) и подтверждением 0 уязвимостей.

### R3. Автоматизированная верификация инфраструктуры и секретов
- **Аудит секретов и окружения**:
  - Проверить `.env.example` на полноту описания всех параметров конфигурации.
  - Убедиться в отсутствии захардкоженных секретов и паролей в репозитории (все секреты передаются исключительно через переменные окружения).
- **Инфраструктурный проверочный оракул (`docs/checks/verify_infra.py`)**:
  - Создать исполняемый скрипт верификации:
    * Проверка синтаксиса и структуры `compose.yaml` и `deploy/nginx.conf`.
    * Валидация согласованности лимита размера файлов между `nginx.conf` (`client_max_body_size 25m`) и кодом бэкенда `files.py` (25 МБ).
    * Проверка наличия тома `storage-data` и non-root директив `USER` в `backend/Dockerfile` и `frontend/Dockerfile`.
    * Проверка наличия заголовков безопасности в `nginx.conf`.
- **Регрессионный контроль (DoD)**:
  - Прогон всех 128 существующих тестов бэкенда (`pytest backend/tests/ -v`) со 100% результатом.
  - Прогон всех проверочных оракулов (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`, `verify_infra.py`).

---

## Acceptance Criteria

### Конфигурация Nginx & Docker (R1)
- [ ] В `deploy/nginx.conf` задан лимит `client_max_body_size 25m;`.
- [ ] В `deploy/nginx.conf` добавлены заголовки `X-Frame-Options`, `X-Content-Type-Options`, `Content-Security-Policy`, `Permissions-Policy`.
- [ ] В `backend/Dockerfile` каталог `/app/storage` создаётся и принадлежит `appuser:appuser`, контейнер запускается от `USER appuser`.
- [ ] В `frontend/Dockerfile` контейнер запускается от `USER nginx`.
- [ ] В `compose.yaml` объявлен том `storage-data` и подключен к сервису `api` по пути `/app/storage`.
- [ ] В `compose.yaml` настроены цепочки `depends_on` с `condition: service_healthy`.

### Безопасность библиотек (R2)
- [ ] Сформирован документ `docs/security/dependency-security-audit.md` с реестром пакетов Python и Node.js.
- [ ] Подтверждено отсутствие известных уязвимостей (0 CVE).
- [ ] Подтверждена архитектурная чистота Ponytail: 0 избыточных библиотек, 6 core-пакетов в `requirements.txt`.

### Автоматизированная проверка и регрессия (R3)
- [ ] `.env.example` содержит полный перечень переменных без захардкоженных секретов в коде.
- [ ] Скрипт `docs/checks/verify_infra.py` создан и возвращает `PASS` по всем проверкам.
- [ ] Все 128 тестов бэкенда (`pytest backend/tests/ -v`) проходят успешно (100% pass rate).
- [ ] Оракулы `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` и `verify_infra.py` возвращают `PASS`.

## Follow-up — 2026-09-20T18:30:05Z

# Backend Architecture, Code Quality & Security Invariants Audit (Part 2 Pre-Defense Audit)

Исчерпывающий аудит серверной архитектуры, чистоты кода по принципам Ponytail и строгого соблюдения инвариантов информационной безопасности (152-ФЗ, ФСТЭК №117, CAS updates, Idempotency) проекта «ИТ Школа Ростелекома — CRM» (rost_crm).

Requested team: 3-agent engineering team (Главный бэкенд-архитектор и код-ревьюер [pro], Аудитор информационной безопасности и 152-ФЗ [pro], QA-инженер автоматизации и стресс-тестирования [flash])

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## References
- docs/planning/01-technical-specification.md — разделы 4 «Жизненный цикл», 5 «Права и роли», 6 «Отчётность».
- docs/planning/02-development-plan.md — задачи B06, B08, B10, B14–B17, B22, B30, B33, B35.
- AGENTS.md — стандарты Ponytail (нулевой оверинжиниринг, минимальный diff), инварианты безопасности (152-ФЗ, 404 Not Found на чужие ID, CAS ревизии, Idempotency-Key).

## Verification Resources
- Существующие 128 тестов: `cd backend && .venv/bin/python -m pytest tests/ -v`
- Оракулы спецификации:
  * `python3 docs/checks/verify_infra.py`
  * `python3 docs/checks/verify_workflow.py`
  * `python3 docs/checks/verify_reports.py`
  * `python3 docs/checks/verify_plan.py`
- Новый стресс-тест конкурентности: `backend/tests/test_core_concurrency_and_security.py`

---

## Requirements

### R1. Архитектура модулей, чистота кода и транзакционность CAS (Backend Lead)
- **Модульный монолит `backend/app/`**:
  - `main.py`: тонкие контроллеры, строгий DI (`Depends`), централизованная обработка ошибок `{error: {code, message, request_id, details}}`.
  - `schemas.py`: строгие Pydantic v2 DTO схемы, валидация типов, запрет несанкционированных полей.
  - `services.py`: полная инкапсуляция бизнес-правил, работа с БД строго через сессию SQLAlchemy.
  - `models.py`: декларативные модели, внешние ключи, индексы и уникальные ограничения.
  - `workflow.py`: детерминированный конечный автомат из 15 состояний (13 рабочих + 2 терминальных) и реестр версий 1 и 2.
- **Ponytail-ревизия**:
  - Устранение мертвого кода, неиспользуемых импортов, дублирующих проверок и избыточных абстракций. Сохранение лаконичности кода.
- **Конкурентность CAS (Compare-And-Swap)**:
  - Гарантия того, что все мутирующие операции (`update_interaction`, `transition`, `assign`, `workflow_migration`, `comments`) атомарно проверяют `expected_revision` и инкрементируют `revision`.
  - При несовпадении ревизии — немедленный откат транзакции (`db.rollback()`) и возврат `HTTP 409 REVISION_CONFLICT`.
- **Идемпотентность (`Idempotency-Key`)**:
  - Проверка таблицы `CommandResult`: повторные запросы с тем же ключом и телом мгновенно возвращают сохранённый ответ без повторного применения мутаций.
  - Проверка валидации длины ключа (непустой, до 200 символов).

### R2. Аудит информационной безопасности (152-ФЗ, ФСТЭК №117) (Security Lead)
- **Изоляция области видимости (Scope Isolation)**:
  - Предикат `scope_clause(user)`: менеджер видит ТОЛЬКО свои карточки (`owner_id == user.id`), руководитель — ТОЛЬКО свою команду (`team_id == user.team_id`), администратор не имеет неявного сквозного доступа к чужим бизнес-данным.
  - **Инвариант сокрытия чужих сущностей (404 Not Found)**:
    * Любой запрос по ID к чужой карточке, вложению или комментарию возвращает строгий `404 Not Found`, а НЕ `403 Forbidden` (предотвращение сканирования ID).
- **Защита файлов и экспортных данных**:
  - Санитайзинг имен файлов в `files.py`: защита от Path Traversal (`../`, абсолютные пути, null-bytes ` `).
  - Защита от Formula Injection в `reports_export.py`: автоматическое экранирование символов `=`, `+`, `-`, `@` апострофом `'`.
- **Неизменяемый журнал аудита (`InteractionEvent`)**:
  - Каждое действие фиксирует темпоральную запись с `user_id`, `actor_name`, `timestamp`, `event_type` и `payload`.

### R3. Автоматизированные стресс-тесты и итоговый отчёт (QA Lead)
- **Стресс-тест конкурентности и безопасности (`backend/tests/test_core_concurrency_and_security.py`)**:
  - Параллельная CAS-гонка: эмуляция 20 одновременных запросов с одинаковой ревизией (ровно 1 успешен, 19 получают 409).
  - Проверка сокрытия: строгий 404 при попытке доступа менеджера к чужому ID карточки, вложения или комментария.
  - Проверка идемпотентности: повтор запроса с тем же `Idempotency-Key` возвращает идентичный результат.
  - Проверка запрета недопустимых переходов workflow.
- **Регрессионный контроль**:
  - Полный прогон `pytest backend/tests/ -v`: все существующие 128+ тестов и новый стресс-тест проходят со 100% успехом.
  - Все 4 проверочных оракула (`verify_infra.py`, `verify_plan.py`, `verify_reports.py`, `verify_workflow.py`) возвращают `PASS`.
- **Итоговый отчёт**:
  - Документ `docs/architecture/code-quality-and-architecture-audit.md` с фиксацией результатов аудита, доказательствами CAS-гарантий, матрицы 152-ФЗ и метрик качества.

---

## Acceptance Criteria

### Архитектура и CAS (R1)
- [ ] Все мутирующие эндпоинты требуют CAS `expected_revision` и заголовок `Idempotency-Key` (до 200 символов).
- [ ] При конфликте ревизии возвращается `HTTP 409 REVISION_CONFLICT` с откатом транзакции.
- [ ] Повторный вызов с тем же `Idempotency-Key` возвращает кэшированный результат без повторного исполнения.
- [ ] Кодовая база очищена от неиспользуемых импортов и мертвого кода по правилам Ponytail.

### Безопасность 152-ФЗ (R2)
- [ ] Попытка доступа к чужим карточкам, вложениям или комментариям возвращает строгий `404 Not Found`.
- [ ] Защита от Path Traversal и Formula Injection валидирована.
- [ ] Каждая мутация сохраняет темпоральную запись `InteractionEvent`.

### Автоматизация и отчётность (R3)
- [ ] Создан тестовый набор `backend/tests/test_core_concurrency_and_security.py` с покрытием параллельных CAS-гонок и проверок 404.
- [ ] Все 128+ тестов (`pytest backend/tests/ -v`) проходят успешно (100% pass rate).
- [ ] Все 4 проверочных оракула возвращают `PASS`.
- [ ] Сформирован отчёт `docs/architecture/code-quality-and-architecture-audit.md`.

## Follow-up — 2026-09-20T22:14:28Z

# Приведение обработки ошибок в backend/app/errors.py к контракту C01

> Status: Launched

Приведение механизма обработки ошибок и валидации в `backend/app/errors.py` в строгое соответствие с контрактом C01 (`docs/architecture/05-contracts-and-parallel-development.md`) с гарантией 100% обратной совместимости.

Requested team: Small, focused team [Model: flash] (Старший Python-разработчик и специалист по API-контрактам)

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## References
- `docs/architecture/05-contracts-and-parallel-development.md` (Контракт C01, раздел 2, строки 32–58)
- `backend/app/errors.py` (Текущая реализация)
- `AGENTS.md` (Принципы Ponytail: минимальный чистый diff, 100% обратная совместимость)

## Verification Resources
- Набор автотестов: `backend/.venv/bin/python -m pytest backend/tests/ -q` (139 тестов)
- Оракулы спецификации:
  * `python3 docs/checks/verify_infra.py`
  * `python3 docs/checks/verify_workflow.py`
  * `python3 docs/checks/verify_reports.py`
  * `python3 docs/checks/verify_plan.py`

---

## Requirements

### R1. Расширение класса APIError и стандартизация формата ошибок C01
- В `backend/app/errors.py`:
  - Расширить сигнатуру конструктора `APIError`:
    ```python
    def __init__(self, code: str, message: str, status: int = 422, details=None, field_errors: list | None = None):
        self.code = code
        self.message = message
        self.status = status
        self.details = details
        self.field_errors = field_errors or []
    ```
  - В обработчике `domain_error` гарантировать наличие ключа `"field_errors": getattr(exc, "field_errors", []) or []` в конверте ответа `{"error": {...}}`.
  - Ключ `details` сохраняется (если `exc.details is not None`), обеспечивая полную обратную совместимость со всеми существующими проверками и клиентами.

### R2. Извлечение ошибок валидации Pydantic и нормализация полей
- В обработчике `RequestValidationError`:
  - Извлекать ошибки полей с удалением префикса `"body"` из пути:
    ```python
    field_errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    ```
  - Передавать `field_errors` и в параметр `details`, и в `field_errors` экземпляра `APIError("VALIDATION_ERROR", "Проверьте поля запроса.", 422, details=field_errors, field_errors=field_errors)`.

### R3. Безопасная обработка непредвиденных исключений (500 Internal Error)
- Добавить глобальный обработчик `@app.exception_handler(Exception)`:
  - Возвращает HTTP 500.
  - JSON-конверт:
    ```json
    {
      "error": {
        "code": "INTERNAL_ERROR",
        "message": "Внутренняя ошибка сервера. Обратитесь к администратору.",
        "request_id": "<correlation-id>",
        "details": null,
        "field_errors": []
      }
    }
    ```
  - Скрывать трассировку стека (traceback), детали SQL-запросов и чувствительные данные от внешнего клиента.

### R4. Регрессионный контроль и сохранение контрактов
- Полный прогон тестового набора `backend/tests/` (139 тестов).
- Никаких регрессий и падений существующих тестов (`139 passed, 0 failed`).
- Отсутствие новых зависимостей (`stdlib`/FastAPI/Starlette only).

---

## Acceptance Criteria

### Контракт ошибок C01
- [ ] Класс `APIError` поддерживает параметр и атрибут `field_errors`.
- [ ] Ответы с ошибками содержат обязательное поле `"field_errors": []` (или список `{field, message}`).
- [ ] В `RequestValidationError` поле `field` нормализуется без префикса `"body"`.
- [ ] Непредвиденные исключения возвращают 500 с кодом `INTERNAL_ERROR` и корректным `request_id`, без утечки stack trace.
- [ ] Сохранена обратная совместимость: поле `details` присутствует при наличии деталей.

### Верификация и стабильность
- [ ] Все 139 существующих автотестов в `backend/tests/` успешно проходят (`139 passed`).
- [ ] Все 4 оракула верификации (`verify_infra.py`, `verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) выдают `PASS`.


## 2026-09-21T08:39:20Z

# Добавление декларативных моделей Delivery и DeliveryItem в backend/app/models.py

> Status: Launched

Добавление моделей SQLAlchemy 2.0 для фиксации фактов передачи материалов, лицензий и документов (`Delivery` и `DeliveryItem`) в `backend/app/models.py` в соответствии с разделом 3 `docs/architecture/02-data-and-workflow.md` и ТЗ.

Requested team: Small, focused team [Model: flash] (Старший инженер баз данных и бэкенд-разработчик)

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## References
- `docs/architecture/02-data-and-workflow.md` (раздел 3, строки 95–96: `delivery`, `delivery_item`)
- `backend/app/models.py` (существующие модели SQLAlchemy 2.0)
- `AGENTS.md` (Принципы Ponytail: лаконичность, отсутствие лишних связей, строгая типизация)

## Verification Resources
- Набор автотестов: `backend/.venv/bin/python -m pytest backend/tests/ -q` (153 существующих теста)
- Проверка импорта моделей: `backend/.venv/bin/python -c "from app.models import Delivery, DeliveryItem; print('Models imported successfully')"`
- Оракулы спецификации:
  * `python3 docs/checks/verify_infra.py`
  * `python3 docs/checks/verify_workflow.py`
  * `python3 docs/checks/verify_reports.py`
  * `python3 docs/checks/verify_plan.py`

---

## Requirements

### R1. Декларативная модель `Delivery` (таблица `deliveries`)
- В `backend/app/models.py` объявить класс `Delivery(Base)`:
  - `__tablename__ = "deliveries"`
  - `id`: `Mapped[str]` (первичный ключ String(64), default=`new_id`)
  - `organization_id`: `Mapped[str]` (ForeignKey `organizations.id`, index=True)
  - `interaction_id`: `Mapped[str | None]` (ForeignKey `interactions.id`, index=True, nullable=True)
  - `status`: `Mapped[str]` (String(32), default="draft") — draft | sent | confirmed | cancelled
  - `channel`: `Mapped[str]` (String(40), default="email")
  - `sent_at`: `Mapped[datetime | None]` (DateTime(timezone=True), nullable=True)
  - `confirmed_at`: `Mapped[datetime | None]` (DateTime(timezone=True), nullable=True)
  - `recipient_contact_id`: `Mapped[str | None]` (ForeignKey `organization_contacts.id`, nullable=True)
  - `recorded_by`: `Mapped[str]` (ForeignKey `users.id`, index=True)
  - `comment`: `Mapped[str | None]` (Text, nullable=True)
  - `created_at`: `Mapped[datetime]` (DateTime(timezone=True), default=`utcnow`)
  - `revision`: `Mapped[int]` (Integer, default=1)

### R2. Декларативная модель `DeliveryItem` (таблица `delivery_items`)
- В `backend/app/models.py` объявить класс `DeliveryItem(Base)`:
  - `__tablename__ = "delivery_items"`
  - `id`: `Mapped[str]` (первичный ключ String(64), default=`new_id`)
  - `delivery_id`: `Mapped[str]` (ForeignKey `deliveries.id`, ondelete="CASCADE", index=True)
  - `item_kind`: `Mapped[str]` (String(32)) — material | document | license
  - `title`: `Mapped[str]` (String(250))
  - `attachment_id`: `Mapped[str | None]` (ForeignKey `attachments.id`, nullable=True)
  - `license_id`: `Mapped[str | None]` (ForeignKey `licenses.id`, nullable=True)
  - `material_version`: `Mapped[str | None]` (String(120), nullable=True)
  - `created_at`: `Mapped[datetime]` (DateTime(timezone=True), default=`utcnow`)

### R3. Регрессионный контроль и целостность БД
- Экспорт и доступность `Delivery` и `DeliveryItem` через `backend/app/models.py`.
- Полное прохождение существующего тестового набора (`153 passed, 0 failed`).
- Отсутствие циклических импортов и ошибок создания таблиц SQLite/PostgreSQL.

---

## Acceptance Criteria

### Модели БД (R1, R2)
- [ ] Классы `Delivery` и `DeliveryItem` объявлены в `backend/app/models.py` с типизацией Mapped/mapped_column SQLAlchemy 2.0.
- [ ] Таблицы `deliveries` и `delivery_items` содержат все требуемые поля, внешние ключи (ForeignKey) и индексы.
- [ ] `DeliveryItem.delivery_id` настроен с каскадным удалением `ondelete="CASCADE"`.

### Верификация и стабильность (R3)
- [ ] Команда `backend/.venv/bin/python -c "from app.models import Delivery, DeliveryItem"` выполняется без ошибок.
- [ ] Добавлены модульные тесты в `backend/tests/test_deliveries_models.py` для проверки валидности создания и сохранения записей `Delivery` и `DeliveryItem`.
- [ ] Все 153+ тестов `pytest backend/tests/ -q` проходят со 100% успехом.
- [ ] Все 4 оракула верификации (`verify_infra.py`, `verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) возвращают `PASS`.



## 2026-09-21T14:05:56Z

Провести беспристрастную фактологическую инвентаризацию исходного кода проекта `rost_crm` по состоянию на Git-тег `audit-baseline-2026-09-21` (коммит `1c7c0eb`), сформировав сухой каталог сущностей, эндпоинтов, сервисов, фронтенда и тестов.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Таблицы и декларативные модели SQLAlchemy
Проанализировать `backend/app/models.py` и `backend/app/db.py`. По каждой модели зафиксировать:
- Имя класса и имя таблицы `__tablename__`.
- Полный перечень колонок, их типы (SQLAlchemy / Python Mapped), признак `nullable`, значения по умолчанию.
- Внешние ключи (`ForeignKey`), составные/уникальные ограничения (`UniqueConstraint`), индексы (`Index`).

### R2. Спецификация HTTP API
Проанализировать зарегистрированные эндпоинты в `backend/app/main.py` и схемы в `backend/app/schemas.py`. Составить сводную таблицу:
- HTTP-метод (`GET`, `POST`, `PATCH`, `DELETE` и др.).
- Точный путь URL с префиксом `/api/v1/`.
- Входные параметры (Path, Query, Headers, Body DTO).
- Применяемые зависимости (`Depends(...)`, проверка токена, проверка роли).
- Возвращаемый HTTP статус-код и схема ответа.

### R3. Сервисные модули и их фактические функции
Проанализировать публичные функции в сервисных модулях:
- `backend/app/services.py`
- `backend/app/workflow.py`
- `backend/app/files.py`
- `backend/app/importer.py`
- `backend/app/reports_export.py`
- `backend/app/integrations/*`
- `backend/app/auth.py`, `backend/app/errors.py`

По каждой функции зафиксировать сигнатуру и аргументы, таблицы БД с операциями (SELECT, INSERT, UPDATE, CAS), поддержку `Idempotency-Key` и `expected_revision`.

### R4. Структура и компоненты Frontend
Проанализировать `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/types.ts` и `frontend/src/views/*`:
- Маршруты и экраны, зарегистрированные в `App.tsx` и доступные через навигационное меню.
- Компоненты вьюх в `frontend/src/views/`, не подключенные к маршрутизатору или меню (сироты).
- Механизм хранения авторизационного токена (in-memory, localStorage, cookies).

### R5. Реестр тестов и сырой вывод pytest
Проанализировать тестовый сьют в `backend/tests/` и бенчмарки в `backend/benchmarks/`:
- Перечень тест-кейсов (`def test_*`) по каждому файлу `test_*.py` с указанием проверяемого инварианта (код ошибки, 404, CAS-конфликт 409, валидация сигнатуры и т.д.).
- Выполнить запуск тестов командой `.venv/bin/pytest -v` (или `backend/.venv/bin/pytest -v`) и включить полный сырой вывод терминала (число пройденных/упавших тестов, время выполнения).

### R6. Ограничения и форматы сдачи
- Запрещено читать любые файлы в `docs/architecture/` и `docs/planning/`.
- Запрещено давать оценочные суждения («хорошо», «плохо», «соответствует ТЗ», «полноценно»).
- Результат сохранить в `.agents/code_inventory_agent/handoff.md` и продублировать в `docs/planning/audit/00-codebase-inventory.md`.
- В шапке отчета зафиксировать дату и коммит `1c7c0eb` (тег `audit-baseline-2026-09-21`).

---

## Acceptance Criteria

### Полнота каталога сущностей и API
- [ ] Описаны все классы моделей из `backend/app/models.py` со всеми колонками, связями и ограничениями.
- [ ] Составлена полная таблица эндпоинтов `/api/v1/` из `backend/app/main.py` с зависимостями авторизации и схемами.
- [ ] Задокументированы публичные функции сервисных модулей с указанием затронутых таблиц и поддержки CAS/идемпотентности.
- [ ] Перечислены активные маршруты фронтенда, изолированные (orphan) компоненты и способ хранения токенов.
- [ ] Составлен реестр тестов из `backend/tests/` с проверяемыми инвариантами.

### Верификация и соблюдение ограничений
- [ ] В отчет включен сырой консольный вывод команды pytest с итоговым статусом и временем выполнения.
- [ ] Созданы два идентичных файла отчета: `.agents/code_inventory_agent/handoff.md` и `docs/planning/audit/00-codebase-inventory.md`.
- [ ] Текст отчета выдержан строго в нейтральном фактологическом стиле (без оценок качества реализации).
- [ ] В отчете отсутствуют ссылки и выдержки из файлов `docs/architecture/` и `docs/planning/`.


## 2026-09-21T16:24:46Z

Провести глубокий аудит соответствия текущей модели данных (`backend/app/models.py`, `docs/planning/audit/00-codebase-inventory.md`) эталонной архитектуре из `docs/architecture/02-data-and-workflow.md` по 6 функциональным блокам сущностей, выявив все расхождения и сформировав план доработок без изменения эталонной архитектуры.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Базовые каталоги, организации и реквизиты (Блок 1)
Сверить фактическое наличие и атрибутивный состав моделей в `models.py` против `docs/architecture/02-data-and-workflow.md`:
- `organization`: наличие `short_name`, `type: university/school/other`, `normalized_name`.
- `organization_identifier`: ведение ИНН/ОГРН и реестровых схем идентификации.
- `organization_contact`: контакты вузов/школ, разделение внешних контактов и внутренних пользователей CRM.
- Справочники продуктов: `vendor`, `direction`, `program`, `product`, `program_product`.
- Таблицы версионирования истории наименований справочников (`organization_version`, `program_version`, `product_version` и др.).

### R2. Договоры, лицензии и факт передачи (Блок 2)
Сверить соответствие сущностей передачи прав и материалов:
- `contract`: номер, интервал дат действия `[valid_from, valid_to]`, дата подписания `signed_on`, статус.
- `license`: продукт, срок `term_years`, статус передачи `transfer_status`, составной FK `(contract_id, organization_id)`.
- `delivery` и `delivery_item`: учет передачи лицензий, учебных материалов и ПО.
- Промежуточные таблицы связей: `interaction_contact`, `interaction_contract`, `interaction_license`.

### R3. Идентичность, команды и разграничение доступа (Блок 3)
Сверить модель прав и владения:
- `app_user`: сохранение строкового PK `id` vs эталон.
- `team` и `team_membership`: управление командами и ролями (manager/supervisor).
- Связка владения карточкой: `interaction.owning_team_id` (FK на `team`) и `owner_id` (nullable для очереди неназначенных).
- `access_policy_state`: наличие счетчика глобальной эпохи `epoch` для инвалидации кэшей политик доступа.

### R4. Карточка взаимодействия и визиты состояний (Блок 4)
Сверить структуру жизненного цикла:
- `interaction`: состав полей, наличие `cycle_label`, `owning_team_id`, `current_state_key`, `current_visit_id`.
- `state_visit`: выделение отдельной сущности визита со временем входа/выхода (`entered_at`, `exited_at`) vs плоское поле в `Interaction`.
- `comment`: привязка комментария к визиту статуса (`state_visit_id`) и событию.

### R5. Неизменяемая история и темпоральные факты (Блок 5)
Сверить версионирование и аудит:
- `interaction_event`: сохранение последовательности `sequence`, временных меток `effective_at` (бизнес-время) и `received_at` (системное время).
- Типизированные исторические факты: выделение специализированных таблиц (`interaction_state_fact`, `interaction_owner_fact`, `interaction_attributes_fact`) vs монолитный `payload` в `interaction_events` / `audit_logs`.

### R6. Интеграции и учебные метрики (Блок 6)
Сверить внешние интеграционные структуры:
- `integration_inbox` / `inbox_message`: структура дедупликации внешних пакетов и сообщений.
- `learning_metrics` / `metric_observation`: модель хранения статистики по потокам и студентам.

### R7. Ограничения, формат отчета и сдача
- **Категорический запрет на модификацию архитектуры:** файлы `docs/architecture/*` неизменяемы (`git diff docs/architecture` должен быть строго пуст).
- Отчет оформляется строго по разделам:
  1. Сводная таблица покрытия моделей (Сущность архитектуры | Статус в коде | Фактическая модель в `models.py` | Ключевые расхождения).
  2. Детальный разбор разрывов (Gaps) с точными ссылками на разделы/строки `02-data-and-workflow.md` и строки `models.py`, с описанием архитектурного влияния.
  3. Рекомендации по доработке кода (Action Items для `backend/app/models.py`).
- Результат сохранить в `.agents/auditor_domain_1_data/handoff.md` и продублировать в `docs/planning/audit/domain-01-data-model.md`.

---

## Acceptance Criteria

### Полнота покрытия архитектурной модели
- [ ] Охвачены все 6 блоков сущностей из `docs/architecture/02-data-and-workflow.md`.
- [ ] Сводная таблица содержит статус реализации для каждой сущности: «Полное соответствие», «Упрощено» или «Отсутствует».
- [ ] По каждому разрыву приведены точные ссылки на разделы/строки архитектуры и строки в `backend/app/models.py`.
- [ ] Для каждого разрыва оценено влияние на безопасность/152-ФЗ, транзакционную целостность, отчетность и миграции.
- [ ] Сформирован пошаговый перечень Action Items для приведения `models.py` к эталону.

### Целостность и артефакты сдачи
- [ ] Созданы два идентичных файла: `.agents/auditor_domain_1_data/handoff.md` и `docs/planning/audit/domain-01-data-model.md`.
- [ ] Файлы эталонной архитектуры `docs/architecture/*` не затронуты (`git status docs/architecture` чист).

## 2026-09-21T17:05:08Z

Провести детальный архитектурный аудит фактической реализации Workflow, конечного автомата (FSM) и механизма миграций карточек в `rost_crm` на соответствие неизменяемой эталонной архитектуре (`docs/architecture/02-data-and-workflow.md`, `docs/architecture/01-target-architecture.md`, `docs/architecture/05-contracts-and-parallel-development.md`), выявив все расхождения и сформировав приоритизированный план доработок.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Базовый граф состояний и переходов
Сверить структуру графа процесса:
- Наличие и соответствие 13 рабочих + 2 терминальных состояний (`completed`, `cancelled`).
- Наличие всех 29 разрешенных переходов между состояниями.
- Физическое хранение графа: зашит ли граф статически в Python-коде/словаре (`workflow.py`) или поддерживается реляционное хранение (`workflow_template`, `workflow_version`, `workflow_state`, `workflow_transition`).

### R2. Декларативные инварианты и гарды (ADR-04)
Сверить валидаторы и защитные условия переходов:
- Блокировка перехода на этап передачи материалов (`materials_transfer`) и далее при отсутствии `program_id` или `product_id` (валидация HTTP 422 `VALIDATION_ERROR`).
- Обязательность комментария при отмене (`cancelled`), возвратах на доработку и повторных циклах.
- Отсутствие механизмов динамического выполнения произвольного кода (`eval`, Python, JS) в логике гардов.

### R3. Жизненный цикл версий процесса (Draft / Published / Retired)
Сверить версионирование шаблонов бизнес-процесса:
- Поддержка жизненного цикла шаблонов (Draft -> Published -> Retired).
- Неизменяемость опубликованных версий и вычисление криптографического хеша (`definition_hash` SHA-256).
- Возможность создания черновика процесса через API (`POST /workflow-templates`) и редактирования этапов без изменения кода приложения.

### R4. Механизм миграции карточек на новые версии (`workflow_migration_plan`)
Сверить двухфазный механизм миграции (`/api/v1/workflow/migrate/preview` и `/commit`):
- Двухфазность: предварительный расчет коллизий ревизий и несмапленных статусов в preview до применения.
- Изоляция терминалов: запрет возврата карточек из `completed` и `cancelled` в активные статусы.
- Атомарность и CAS: проверка `expected_revision` для каждой мигрируемой карточки.
- Аудит миграции: формирование системного события `workflow_migrated` с исключением из операционной бизнес-воронки.

### R5. Конкурентность и транзакционные гарантии переходов
Сверить устойчивость к параллельным операциям:
- Защита от race condition через строгий CAS-апдейт (`WHERE id = :id AND revision = :expected_revision`).
- Проверка и сохранение `Idempotency-Key` для исключения повторных побочных эффектов.
- Генерация неизменяемых событий `interaction_events` с монотонно растущим `sequence`.

### R6. Ограничения, структура отчета и сдача
- **Категорический запрет на изменение архитектуры:** файлы `docs/architecture/*` неизменяемы (`git diff docs/architecture` строго пуст).
- Исходный код `backend/` не модифицируется в процессе аудита.
- Структура отчета:
  1. Сводная таблица соответствия Workflow (Требование эталона | Статус в коде | Реализация: файлы и строки | Расхождения).
  2. Детальный разбор архитектурных разрывов со ссылками на строки архитектуры и кода, с оценкой риска.
  3. Сырые доказательства (Raw Evidence): выдержки кода проверок условий/CAS, сырой вывод запуска тестов `test_workflow_migration.py` и `test_working_slice.py`.
  4. Приоритизированный перечень Action Items.
- Сохранить результат в `.agents/auditor_domain_2_workflow/handoff.md` и продублировать в `docs/planning/audit/domain-02-workflow.md`.

---

## Acceptance Criteria

### Полнота охвата и глубина анализа
- [ ] Охвачены все 5 аспектов (базовый граф, гарды/инварианты, жизненный цикл шаблонов, двухфазная миграция, конкурентность/CAS).
- [ ] Сводная таблица содержит статусы «Полное соответствие», «Упрощено» или «Отсутствует».
- [ ] Все разрывы содержат точные ссылки на строки в `docs/architecture/` и `backend/app/`.
- [ ] Проведен анализ рисков для целостности FSM, миграций и транзакционной безопасности.
- [ ] Приведены сырые доказательства (выдержки кода и подтвержденный прогон тестов).
- [ ] Сформирован конкретный список Action Items для устранения разрывов.

### Целостность и артефакты сдачи
- [ ] Созданы два идентичных файла: `.agents/auditor_domain_2_workflow/handoff.md` и `docs/planning/audit/domain-02-workflow.md`.
- [ ] Файлы эталонной архитектуры `docs/architecture/*` не затронуты (`git status docs/architecture` чист).
- [ ] Исходный код backend не изменялся.


## 2026-09-21T17:46:33Z

Провести глубокий архитектурный аудит фактической реализации фоновых задач (Jobs), файловой подсистемы (Attachments/Storage) и аналитической отчетности (Reports Export) в `rost_crm` на соответствие неизменяемой эталонной архитектуре (`docs/architecture/03-jobs-files-integrations-reports.md`, `docs/architecture/01-target-architecture.md`, `docs/architecture/05-contracts-and-parallel-development.md`), выявив все расхождения и составив приоритизированный план доработок по принципам Ponytail.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Фоновые задачи и надежное исполнение (Jobs & Workers)
Сверить архитектурный стиль исполнения асинхронных операций:
- Способ исполнения генерации отчетов и обработки файлов: синхронно в рамках HTTP-запроса FastAPI vs асинхронный брокер/воркеры (Celery + Redis).
- Наличие в моделях БД сущностей `background_job`, `job_attempt`, `outbox_event`.
- Обеспечение требования ТЗ по одновременному расчету не менее 10 параллельных отчетов и риск блокировки пула потоков FastAPI/Uvicorn.

### R2. Файловая подсистема и безопасность вложений
Сверить механизмы валидации, хранения и скачивания файлов:
- Строгое соблюдение белого списка 10 разрешенных расширений (`png`, `jpeg`, `pdf`, `zip`, `gzip`, `rar`, `doc`, `docx`, `xls`, `xlsx`).
- Проверка сигнатур (Magic Bytes) и отсечение исполняемых файлов (PE `.exe`, ELF) и веб-скриптов.
- Соблюдение лимита размера 25 МБ (`FILE_TOO_LARGE`, HTTP 413) и вычисление SHA-256 хеша.
- Хранилище и изоляция путей: локальная файловая система под UUID (`storage/attachments/`) vs S3-совместимый `StoragePort`; исключение прямого публичного доступа мимо авторизованного API.
- Наличие карантина и антивирусного сканирования (`pending_scan` -> ClamAV -> `clean`).

### R3. Аналитическая отчетность и многоформатный экспорт
Сверить движок формирования и экспорта аналитики:
- Поддержка трех регламентных режимов: `snapshot` (на дату `as_of`), `activity` (переходы за период `[from, to)`), `created` (созданные карточки за `[from, to)`).
- Поддержка экспорта в форматы ТЗ: XLSX (OpenXML zip/xml), XLS (бинарный BIFF8), векторный PDF с кириллицей, канонический JSON UTF-8.
- Защита от Formula Injection: экранирование начальных символов ячеек (`=`, `+`, `-`, `@`).
- Неизменяемость датасета (Frozen Dataset): материализация строк отчета в таблицы `report_run` и `report_row` перед рендерингом vs генерация на лету.

### R4. Ограничения, структура отчета и сдача
- **Категорический запрет на изменение архитектуры:** файлы `docs/architecture/*` неизменяемы (`git diff docs/architecture` строго пуст).
- Исходный код `backend/` не модифицируется в процессе аудита.
- Структура отчета:
  1. Сводная таблица соответствия Домена 3 (Требование эталона | Статус в коде | Реализация: файлы и строки | Выявленные разрывы).
  2. Детальный разбор архитектурных разрывов с ссылками на строки и оценкой риска.
  3. Сырые доказательства (Raw Evidence): выдержки кода проверок magic bytes / санитизации формул, сырой вывод запуска тестов `backend/tests/test_attachments.py` и `backend/tests/test_reports_multiformat.py`.
  4. Приоритизированный перечень Action Items по Ponytail (P0 — безопасность и валидность форматов, P1 — frozen dataset, P2 — Celery/Redis).
- Сохранить результат в `.agents/auditor_domain_3_jobs_files_reports/handoff.md` и продублировать в `docs/planning/audit/domain-03-jobs-files-reports.md`.

---

## Acceptance Criteria

### Полнота охвата и глубина анализа
- [ ] Охвачены все 3 функциональных направления (фоновые задачи/воркеры, файловая безопасность, отчетность и экспорт).
- [ ] Сводная таблица содержит статусы «Полное соответствие», «Упрощено» или «Отсутствует».
- [ ] Все разрывы содержат точные ссылки на строки в `docs/architecture/` и `backend/app/`.
- [ ] Проведен анализ рисков (блокировка воркеров, уязвимости вложений, десинхронизация форматов отчетов).
- [ ] Приведены сырые доказательства (выдержки кода и подтвержденный прогон тестов).
- [ ] Сформирован перечень Action Items с приоритизацией P0, P1, P2.

### Целостность и артефакты сдачи
- [ ] Созданы два идентичных файла: `.agents/auditor_domain_3_jobs_files_reports/handoff.md` и `docs/planning/audit/domain-03-jobs-files-reports.md`.
- [ ] Файлы эталонной архитектуры `docs/architecture/*` не затронуты (`git status docs/architecture` чист).
- [ ] Исходный код backend не изменялся.


## 2026-09-21T18:22:50Z

Провести глубокий архитектурный аудит фактической реализации подсистемы интеграций (LMS, сайт на Laravel, очередь сверки Inbox, канонический конверт и учебные метрики) в `rost_crm` на соответствие неизменяемой эталонной архитектуре (`docs/architecture/03-jobs-files-integrations-reports.md`, `docs/architecture/01-target-architecture.md`, `docs/architecture/05-contracts-and-parallel-development.md`), выявив все расхождения и составив приоритизированный план доработок по принципам Ponytail.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Архитектура адаптеров (SourceAdapter Pattern)
Сверить структуру адаптеров внешних систем:
- Наличие и интерфейс абстрактного базового класса/протокола `SourceAdapter` с методами `check_connection()`, `fetch_page()`, `normalize()`.
- Реализация специализированных адаптеров для LMS ИТ Школы РТК (учебные метрики) и веб-сайта на Laravel (входящие заявки от вузов).
- Конфигурируемость фабрики адаптеров (`factory.py`) и безопасное переключение между автономным Mock-режимом и Live HTTP-клиентами.

### R2. Канонический конверт (CanonicalEnvelope) и дедупликация в Inbox
Сверить формат нормализованных сообщений и механизм защиты от дублей:
- Соответствие структуры конверта контракту `C07` (`schema_version`, `source`, `entity_type`, `external_id`, `source_revision`, `effective_at`, `payload`).
- Дедупликация на уровне БД в таблице `IntegrationInbox`: составной уникальный ключ `uq_inbox_dedup(source, entity_type, external_id, source_revision)`.
- Поведение при повторной доставке пакета с идентичным идентификатором и ревизией (блокировка повторного создания сущностей).

### R3. Очередь сверки коллизий (Reconciliation Inbox) и управление карточками
Сверить логику обработки неопознанных партнерских заявок:
- Изоляция заявок с неизвестными CRM вузами в статус `pending` в очереди `IntegrationInbox`.
- Интерфейс разрешения коллизий (`POST /api/v1/integrations/inbox/{id}/resolve`): поддержка действий `link_existing`, `create_new`, `reject`.
- Разграничение доступа (152-ФЗ / Scope) при автосоздании взаимодействия: привязка к ответственному менеджеру (`owner_id`) и команде (`team_id`).

### R4. Контур учебных метрик (Learning Metrics)
Сверить модель хранения и витрину образовательной аналитики:
- Структура персистентности метрик в таблице `LearningMetric` (код, значение, единица измерения, дата `as_of`, источник).
- Эндпоинт агрегированной витрины `GET /api/v1/integrations/metrics` с фильтрами по `organization_id` и `program_id`.
- Сравнение с эталонной моделью `metric_observation` и `learning_cohort` из `02-data-and-workflow.md`.

### R5. Ограничения, структура отчета и сдача
- **Категорический запрет на изменение архитектуры:** файлы `docs/architecture/*` неизменяемы (`git diff docs/architecture` строго пуст).
- Исходный код `backend/` не модифицируется в процессе аудита.
- Структура отчета:
  1. Сводная матрица соответствия Домена 4 (Требование эталона | Статус в коде | Реализация: файлы и строки | Выявленные разрывы).
  2. Детальный разбор архитектурных разрывов с ссылками на строки и оценкой рисков.
  3. Сырые доказательства (Raw Evidence): выдержки кода `CanonicalEnvelope`, дедупликации, резолвинга коллизий, сырой вывод тестов `test_integrations.py` и `test_adversarial_integrations.py`.
  4. Приоритизированный перечень Action Items по Ponytail (P0 — надежность дедупликации и Scope, P1 — курсоры и webhook, P2 — live-адаптеры).
- Сохранить результат в `.agents/auditor_domain_4_integrations/handoff.md` и продублировать в `docs/planning/audit/domain-04-integrations.md`.

---

## Acceptance Criteria

### Полнота охвата и глубина анализа
- [ ] Охвачены все 4 аспекта (адаптеры источников, канонический конверт и дедупликация, очередь сверки/резолвинг коллизий, учебные метрики).
- [ ] Сводная матрица содержит статусы «Полное соответствие», «Упрощено» или «Отсутствует».
- [ ] Все выявленные разрывы содержат точные ссылки на строки в `docs/architecture/` и `backend/app/`.
- [ ] Проведен анализ рисков (дублирование сущностей, потеря заявок, десинхронизация курсоров, утечка доступа по 152-ФЗ).
- [ ] Приведены сырые доказательства (выдержки кода и подтвержденный прогон тестов).
- [ ] Сформирован приоритизированный перечень Action Items (P0, P1, P2).

### Целостность и артефакты сдачи
- [ ] Созданы два идентичных файла: `.agents/auditor_domain_4_integrations/handoff.md` и `docs/planning/audit/domain-04-integrations.md`.
- [ ] Файлы эталонной архитектуры `docs/architecture/*` не затронуты (`git status docs/architecture` чист).
- [ ] Исходный код backend не изменялся.


## 2026-09-21T18:52:37Z

Провести глубокий архитектурный аудит фактической реализации подсистемы аутентификации, разграничения доступа (RBAC), изоляции данных по 152-ФЗ и требований приказа ФСТЭК № 117 в проекте `rost_crm` на соответствие неизменяемой эталонной архитектуре (`docs/architecture/01-target-architecture.md`, `docs/architecture/c4-architecture.md`, `docs/architecture/code-quality-and-architecture-audit.md`), выявив все расхождения и составив приоритизированный план доработок по принципам Ponytail.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Хранение и жизненный цикл JWT-токенов
Сверить реализацию клиентской аутентификации в `frontend/src/auth.tsx` и `frontend/src/api.ts`:
- Удержание токенов Keycloak строго в оперативной памяти браузера (in-memory, `useRef` / замыкания).
- Подтверждение полного отсутствия сохранения токенов в `localStorage`, `sessionStorage` и `IndexedDB`.
- Механизм упреждающего обновления токенов (`updateToken(30)`) и поведение при истечении пользовательской сессии.

### R2. Разграничение доступа (RBAC & Scope Isolation)
Сверить логику предикатов `scope_clause(user)` и `scoped_interaction()` в `backend/app/services.py`:
- Менеджер (`manager`): доступ только к карточкам, где он является `owner_id`, либо организациям с явным флагом `OrganizationAccess.read_all == True`.
- Руководитель (`supervisor`): доступ только к карточкам своей команды `Interaction.team_id == user.team_id` и назначенным организациям.
- Администратор (`admin`): техническая роль — исключение неявного доступа к коммерческим карточкам взаимодействий без явного назначения `OrganizationAccess`.

### R3. Сокрытие сущностей по 152-ФЗ (Strict 404 vs 403)
Сверить поведение API при прямом обращении по ID к чужим объектам:
- Возврат строгого **HTTP 404 Not Found** (сокрытие факта существования записи) вместо HTTP 403 Forbidden при попытке доступа к взаимодействию чужой команды или чужого менеджера.
- Проверка отсутствия утечек идентификаторов через сообщения об ошибках, автодополнение или списочные фильтры.

### R4. Инвалидация кэша прав и `authz_epoch`
Сверить статус архитектурного требования к `access_policy_state.epoch` / `authz_epoch`:
- Реализована ли глобальная эпоха прав в моделях и СУБД.
- Оценка необходимости эпохи в текущем синхронном профиле работы API (динамический расчет `scope_clause` на каждый SQL-запрос без кэширования vs требование к фоновым отчетам).
- Классификация статуса: полное соответствие / осознанное упрощение (YAGNI) / архитектурный долг.

### R5. Конфигурация Keycloak и минимизация ПДн
Сверить настройки OIDC Realm и аудит логов:
- Конфигурация `deploy/keycloak/rtk-crm-realm.json`: клиенты, роли (`manager`, `supervisor`, `admin`), алгоритмы подписи (RS256) и поддержка PKCE (S256).
- Аудит логов: исключение персональных данных, паролей и токенов сессий из логов запросов и трейсов.

### R6. Ограничения, структура отчета и сдача
- **Категорический запрет на изменение архитектуры:** файлы `docs/architecture/*` неизменяемы (`git diff docs/architecture` строго пуст).
- Исходный код `backend/` и `frontend/` не модифицируется в процессе аудита.
- Структура отчета:
  1. Executive Summary (соответствие 152-ФЗ, ФСТЭК №117 и разделу 6 эталона).
  2. Сводная матрица соответствия Домена 5 (Требование эталона | Статус в коде | Файлы и строки | Разрывы и риски).
  3. Детальный разбор разрывов со ссылками на строки `auth.py`, `services.py`, `auth.tsx`.
  4. Сырые доказательства (Raw Evidence): выдержки кода `scope_clause` / `scoped_interaction`, сырой вывод тестов `test_core_concurrency_and_security.py`.
  5. Приоритизированный перечень Action Items по Ponytail (P0 — инварианты изоляции, P1 — аудит и политики, P2 — глобальная эпоха).
- Сохранить результат в `.agents/auditor_domain_5_security/handoff.md` и продублировать в `docs/planning/audit/domain-05-security.md`.

---

## Acceptance Criteria

### Полнота охвата и глубина анализа
- [ ] Охвачены все 5 направлений (жизненный цикл JWT, RBAC & Scope, сокрытие по 152-ФЗ, authz_epoch, конфигурация Keycloak / минимизация ПДн).
- [ ] Сводная матрица содержит статусы «Полное соответствие», «Упрощено» или «Отсутствует».
- [ ] Все разрывы содержат точные ссылки на строки в `docs/architecture/` и исходном коде (`backend/app/`, `frontend/src/`).
- [ ] Проведен строгий анализ рисков утечки данных, обхода прав и соответствия требованиям ФСТЭК № 117.
- [ ] Приведены сырые доказательства (выдержки кода и подтвержденный прогон тестов безопасности).
- [ ] Сформирован перечень Action Items по принципам Ponytail (P0, P1, P2).

### Целостность и артефакты сдачи
- [ ] Созданы два идентичных файла: `.agents/auditor_domain_5_security/handoff.md` и `docs/planning/audit/domain-05-security.md`.
- [ ] Файлы эталонной архитектуры `docs/architecture/*` не затронуты (`git status docs/architecture` чист).
- [ ] Исходный код backend и frontend не изменялся.

## 2026-09-21T19:32:09Z

Провести глубокий архитектурный аудит фактической реализации клиентского приложения SPA, пользовательского опыта (UX), маршрутизации и дизайн-системы Ростелекома Gen2 Light в проекте `rost_crm` на соответствие эталонной архитектуре (`docs/architecture/01-target-architecture.md`, `docs/architecture/c4-architecture.md`, `AGENTS.md`, `docs/planning/08-ui-design-system-analysis.md`), выявив все расхождения и составив приоритизированный план доработок по принципам Ponytail.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Маршрутизация и статус представлений
Сверить структуру маршрутов и компонентов в `frontend/src/App.tsx`, `frontend/src/hooks.ts` и `frontend/src/views/*`:
- Наличие и доступность в навигации экранов `CatalogPage.tsx` (`#catalogs`) и `IntegrationsView.tsx` (`#integrations` для ролей supervisor/admin).
- Архитектурный статус `WorkflowGraphView.tsx`: проверка встраивания в `InteractionPage.tsx` (строка 533) vs статус самостоятельного экрана.
- Проверка наличия неиспользуемых компонентов, мёртвого кода или тупиковых ссылок в кодовой базе фронтенда.

### R2. Принцип неперезагружаемости (Zero-Reload SPA) и обработка форм
Сверить эргономику и обработку пользовательских действий:
- Полное исключение перезагрузки окна браузера (`window.location.reload()`, стандартный submit форм без `preventDefault`) при смене этапов воронки, отправке комментариев, загрузке вложений и смене фильтров.
- Гарантия сохранения черновика введённого текста при серверных ошибках валидации (HTTP 422 `VALIDATION_ERROR`, 409 `REVISION_CONFLICT`).
- Единый формат и отображение серверных ошибок (`code`, `message`, `request_id`, `field_errors`).

### R3. Дизайн-система Ростелекома Gen2 Light Theme
Сверить визуальный слой и дизайн-токены:
- Цветовая палитра: основной бренд `#7700FF` / `#6C00E0`, акцент `#FF4F12` / `#FF6A13`, нейтральный рабочий фон `#F4F5F8`, карточки `#FFFFFF`.
- Типографика и доступность: основной текст `#101828` с контрастностью > 10:1.
- Компонентная реализация: степпер 14 этапов жизненного цикла взаимодействия, доступность карточки на мобильных и узких экранах без обязательного drag-and-drop.

### R4. Оценка по принципам Ponytail Ladder
Оценить лаконичность и архитектурную чистоту фронтенда:
- Анализ `frontend/package.json`: отсутствие избыточных UI-фреймворков (MUI, AntD) и календарных библиотек (Moment, Dayjs).
- Использование нативных стандартов браузера (`<input type="date">`, CSS Grid/Flexbox, `fetch`/`ApiClient`).
- Выявление зон необоснованного усложнения и предложений по минимизации кода.

### R5. Ограничения, структура отчета и сдача
- **Категорический запрет на изменение архитектуры:** файлы `docs/architecture/*` неизменяемы (`git diff docs/architecture` строго пуст).
- Исходный код `frontend/` и `backend/` не модифицируется в процессе аудита.
- Структура отчета:
  1. Executive Summary (соответствие разделу 7 эталона и дизайн-системе Gen2).
  2. Сводная матрица соответствия Домена 6 (Требование эталона | Статус в коде | Файлы и строки | Разрывы и замечания).
  3. Детальный разбор разрывов (маршрутизация, обработка ошибок, эргономика, дизайн-система).
  4. Сырые доказательства (Raw Evidence): выдержки из `App.tsx`, `InteractionPage.tsx`, `auth.tsx`, CSS-токенов, анализ `package.json`.
  5. Приоритизированный перечень Action Items по Ponytail (P0, P1, P2).
- Сохранить результат в `.agents/auditor_domain_6_frontend_ux/handoff.md` и продублировать в `docs/planning/audit/domain-06-frontend-ux.md`.

---

## Acceptance Criteria

### Полнота охвата и глубина анализа
- [ ] Охвачены все 4 направления (маршрутизация/сироты, zero-reload SPA и сохранение форм, дизайн-система Gen2 Light, аудит зависимостей Ponytail).
- [ ] Сводная матрица содержит статусы «Полное соответствие», «Упрощено» или «Отсутствует».
- [ ] Все разрывы содержат точные ссылки на строки в `docs/architecture/` и `frontend/src/`.
- [ ] Проверен контраст цветов, адаптивность и отсутствие полных перезагрузок браузера.
- [ ] Приведены сырые доказательства (выдержки кода, CSS-переменных, зависимостей `package.json`).
- [ ] Сформирован перечень Action Items по принципам Ponytail (P0, P1, P2).

### Целостность и артефакты сдачи
- [ ] Созданы два идентичных файла: `.agents/auditor_domain_6_frontend_ux/handoff.md` и `docs/planning/audit/domain-06-frontend-ux.md`.
- [ ] Файлы эталонной архитектуры `docs/architecture/*` не затронуты (`git status docs/architecture` чист).
- [ ] Исходный код frontend и backend не изменялся.

## 2026-09-21T20:04:51Z

Провести глубокий архитектурный аудит фактической производительности, задержек (Latency SLA $\le 1.0\text{ с}$), устойчивости к конкурентной нагрузке (50 одновременных пользователей и 10 параллельных отчетов), лимитов пулов AnyIO/СУБД и масштабируемости в проекте `rost_crm` на соответствие эталонной архитектуре (`docs/architecture/01-target-architecture.md`, `c4-architecture.md`, `docs/planning/01-technical-specification.md`), выявив все расхождения и составив приоритизированный план оптимизаций по принципам Ponytail Ladder.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Бюджет интерфейсной секунды (Инвариант $\le 1.0\text{ с}$)
Сверить фактические показатели задержки из протокола `docs/benchmarks/load-test-report.md` и скрипта `backend/benchmarks/benchmark_load.py` с эталонными требованиями:
- Фактические задержки P95 и P99 по категориям `interactive`, `analytical`, `administrative`.
- Разложение задержки по бюджетам эталона: network+proxy $\le 150$ мс, API+DB $\le 550$ мс, render $\le 200$ мс.
- Оценка максимальных задержек (Max Latency) под пиковой нагрузкой и соблюдение жесткого потолка в 1.0 с.

### R2. Профиль нагрузки 50 одновременных пользователей
Сверить соответствие нагрузочного профиля разделу 8 целевой архитектуры:
- Распределение запросов: 60% чтение/фильтры, 25% карточки, 10% комментарии, 5% переходы/назначения.
- Поведение системы при 50 одновременных сессиях разных ролей (`manager`, `supervisor`, `admin`).
- Процент ошибок (Error Rate) и устойчивость к гонкам данных (Race Conditions, CAS-конфликты 409).

### R3. Параллельное построение отчетов (10 одновременных выгрузок)
Сверить соблюдение норматива параллельной генерации не менее 10 тяжёлых аналитических отчетов:
- Обработка одновременных запросов на расчет и рендеринг (Snapshot, Activity, Created, XLSX, PDF).
- Конкуренция за ресурсы между быстрыми интерактивными запросами и тяжёлыми выгрузками.
- Риск взаимных блокировок (Deadlocks) или голодания потоков (Thread Starvation).

### R4. Пул потоков AnyIO и пул соединений СУБД
Сверить конфигурацию серверного рантайма и пулов:
- Лимитер потоков AnyIO: проверка установки `anyio.to_thread.current_default_thread_limiter().total_tokens = 120` в боевом `backend/app/main.py`.
- Пул соединений SQLAlchemy: параметры `pool_size` и `max_overflow` в `backend/app/db.py` для SQLite и PostgreSQL.
- Настройки режима работы SQLite (WAL mode, `synchronous=NORMAL`) для локального/демо стенда против требований к PostgreSQL в промышленном контуре.

### R5. Оценка архитектурных компромиссов по Ponytail Ladder
Оценить текущее решение синхронной генерации отчетов в сравнении с эталонной моделью Celery+Redis:
- Обоснованность синхронного расчета в пуле потоков FastAPI для этапа хакатона (Gate D).
- Определение конкретных эмпирических порогов (объем базы, количество строк отчета), требующих обязательного внедрения асинхронных воркеров.

### R6. Ограничения, структура отчета и сдача
- **Категорический запрет на изменение архитектуры:** файлы `docs/architecture/*` неизменяемы (`git diff docs/architecture` строго пуст).
- Исходный код `backend/` и `frontend/` не модифицируется в процессе аудита.
- Структура отчета:
  1. Executive Summary (резюме соответствия нормативам R18/R19 и разделу 8 эталона).
  2. Сводная матрица соответствия Домена 7 (Требование эталона | Статус в кодовой базе | Файлы, замеры, строки | Разрывы и риски).
  3. Детальный разбор нагрузочных профилей и замеров (сравнение бюджетов с данными бенчмарка).
  4. Сырые доказательства (Raw Evidence): выдержки из `benchmark_load.py`, `load-test-report.md`, конфигурации AnyIO в `main.py` и пула в `db.py`.
  5. Приоритизированный перечень Action Items по Ponytail (P0, P1, P2).
- Сохранить результат в `.agents/auditor_domain_7_performance/handoff.md` и продублировать в `docs/planning/audit/domain-07-performance.md`.

---

## Acceptance Criteria

### Полнота охвата и глубина анализа
- [ ] Охвачены все 5 направлений (бюджет $\le 1.0\text{ с}$, профиль 50 пользователей, 10 параллельных отчетов, пулы AnyIO/БД, оценка компромиссов по Ponytail).
- [ ] Сводная матрица содержит статусы «Полное соответствие», «Упрощено» или «Отсутствует».
- [ ] Все выводы подкреплены конкретными эмпирическими замерами из `load-test-report.md` и ссылками на строки кода.
- [ ] Проведен строгий анализ рисков исчерпания пула потоков AnyIO и конкуренции интерактивной/аналитической нагрузки.
- [ ] Приведены сырые доказательства (выдержки кода конфигурации пулов и логи замеров бенчмарка).
- [ ] Сформирован приоритизированный перечень Action Items по принципам Ponytail (P0, P1, P2).

### Целостность и артефакты сдачи
- [ ] Созданы два идентичных файла: `.agents/auditor_domain_7_performance/handoff.md` и `docs/planning/audit/domain-07-performance.md`.
- [ ] Файлы эталонной архитектуры `docs/architecture/*` не затронуты (`git status docs/architecture` чист).
- [ ] Исходный код backend и frontend не изменялся.


## 2026-09-21T20:47:12Z

Провести глубокий архитектурный аудит инфраструктуры, Docker-контейнеризации, безопасности сред (non-root, секреты), интеграции OIDC Keycloak, проб жизнеспособности (healthchecks) и готовности к эксплуатации в проекте `rost_crm` на соответствие эталонной целевой архитектуре (`docs/architecture/01-target-architecture.md`, `c4-architecture.md`, `AGENTS.md`), выявив все расхождения и составив приоритизированный план доработок по принципам Ponytail Ladder.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Безопасность Docker-образов и процессов (Non-Root Privilege)
Сверить директивы `Dockerfile` бэкенда (`backend/Dockerfile`) и фронтенда (`frontend/Dockerfile`):
- Создание и использование выделенного непривилегированного пользователя (`appuser` с фиксированным UID 10001 в бэкенде, `nginx` во фронтенде).
- Явная инструкция `USER` перед запуском процесса контейнера.
- Ограничение прав доступа на каталог локального файлового хранилища (`/app/storage`).

### R2. Управление секретами и изоляция сетевого периметра
Сверить манифесты `compose.yaml` и `.env.example`:
- Отсутствие захардкоженных секретов в Git: передача всех паролей (`POSTGRES_ADMIN_PASSWORD`, `CRM_DB_PASSWORD`, `KEYCLOAK_DB_PASSWORD`, `KEYCLOAK_ADMIN_PASSWORD`) через защищенный синтаксис `${VAR:?error}`.
- Изоляция сетевого периметра: порт PostgreSQL (5432) изолирован строго во внутренней сети Docker (`internal_network`) без публикации на хост.
- Публикация веб-сервисов: привязка внешних портов Keycloak (8080) и фронтенда (3000) строго к локальному интерфейсу `127.0.0.1`.

### R3. Пробы готовности и жизнеспособности (Healthchecks)
Сверить реализацию probe-механизмов в `compose.yaml` и `backend/app/main.py`:
- Эндпоинт `/health/live`: валидация непрерывной работы процесса.
- Эндпоинт `/health/ready`: проверка реального подключения к СУБД (`SELECT 1`) без утечки стектрейсов и параметров подключения при сбоях (возврат HTTP 503 `NOT_READY`).
- Наличие проверок healthcheck в `compose.yaml` для всех контейнеров: PostgreSQL (`pg_isready`), Keycloak (`/health/ready`), API (`urllib.request`) и Frontend (`wget /_frontend_health`).
- Наличие строгой цепочки зависимостей запуска через `depends_on: {condition: service_healthy}`.

### R4. Схема базы данных, миграции и инициализация
Сверить механизм подготовки схемы СУБД:
- Текущий способ создания схемы (`python -m app.seed --init-db` через `Base.metadata.create_all`) vs требование раздела 9 эталона (выполнение версионируемых миграций Alembic отдельным release job).
- Оценка статуса: обоснованное упрощение для демо/хакатона (Gate D) vs архитектурный долг для промышленного контура (Gate P/O).

### R5. Защитные заголовки и обратный прокси (Nginx & CSP)
Сверить конфигурацию `deploy/nginx.conf`:
- Наличие заголовков безопасности: `X-Frame-Options`, `X-Content-Type-Options nosniff`, `Referrer-Policy`, `Permissions-Policy`.
- Content Security Policy (CSP): корректность директив для SPA и авторизации через Keycloak OIDC.
- Ограничение размера тела запроса (`client_max_body_size 25m`) в соответствии с лимитом ТЗ на загрузку файлов.

### R6. Ограничения, структура отчета и сдача
- **Категорический запрет на изменение архитектуры:** файлы `docs/architecture/*` неизменяемы (`git diff docs/architecture` строго пуст).
- Исходный код `backend/`, `frontend/` и инфраструктурные манифесты не модифицируются в процессе аудита.
- Структура отчета:
  1. Executive Summary (резюме соответствия разделу 9 эталона, требованиям DevSecOps и безопасности).
  2. Сводная матрица соответствия Домена 8 (Требование эталона | Статус в коде/манифестах | Файлы и строки | Разрывы и риски).
  3. Детальный разбор инфраструктурных разрывов (non-root, secrets, health probes, network isolation, migrations).
  4. Сырые доказательства (Raw Evidence): выдержки из `compose.yaml`, `Dockerfile`, `nginx.conf`, `main.py`, результаты проверки healthcheck.
  5. Приоритизированный перечень Action Items по Ponytail (P0, P1, P2).
- Сохранить результат в `.agents/auditor_domain_8_deployment_infra/handoff.md` и продублировать в `docs/planning/audit/domain-08-deployment-infra.md`.

---

## Acceptance Criteria

### Полнота охвата и глубина анализа
- [ ] Охвачены все 5 направлений (безопасность контейнеров non-root, секреты/сеть, health probes, миграции Alembic vs create_all, Nginx/CSP).
- [ ] Сводная матрица содержит статусы «Полное соответствие», «Упрощено» или «Отсутствует».
- [ ] Все выводы подкреплены точными ссылками на строки в `compose.yaml`, `Dockerfile`, `nginx.conf`, `main.py`, `docs/architecture/`.
- [ ] Проведен анализ рисков безопасности, утечки секретов и доступности сервисов.
- [ ] Приведены сырые доказательства (выдержки конфигураций и проверочных команд).
- [ ] Сформирован перечень Action Items с приоритизацией P0, P1, P2.

### Целостность и артефакты сдачи
- [ ] Созданы два идентичных файла: `.agents/auditor_domain_8_deployment_infra/handoff.md` и `docs/planning/audit/domain-08-deployment-infra.md`.
- [ ] Файлы эталонной архитектуры `docs/architecture/*` не затронуты (`git status docs/architecture` чист).
- [ ] Исходный код и конфигурационные файлы не изменялись.


## 2026-09-22T11:02:15Z

Свести и актуализировать мастер-документ архитектурного разрыва `docs/planning/07-gap-analysis.md` на основе 8 проведенных доменных аудитов (`domain-01` — `domain-08`), фактической инвентаризации кодовой базы и эталонной архитектуры `rost_crm` (baseline `1c7c0eb`) в строгом соответствии с принципами Ponytail Ladder.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Executive Summary и общая статистика зрелости решения
Сформировать аналитическое резюме состояния кодовой базы на момент завершения 8 доменных аудитов:
- Статистика готовности к защите прототипа (Gate D) и перехода к пилоту (Gate P / Gate O).
- Процентное соотношение: полное соответствие (Full Compliance), обоснованные упрощения (Ponytail Simplification), несоответствия/риски (Discrepancies/Risks), отсутствующий функционал (Missing/Deferred).
- Оценка соблюдения фундаментальных инвариантов: 152-ФЗ, ФСТЭК №117, Non-Root контейнеризация, CAS-конкурентность, 15 состояний воронки, in-memory JWT.

### R2. Актуализированная сводная матрица требований (R01–R30)
Полностью переработать и актуализировать устаревшую матрицу требований от 19 сентября на основе реального кода и доменных отчетов:
- Колонки: `ID` | `Требование ТЗ` | `Статус в коде (Реализовано / Упрощено / Частично / Не реализовано)` | `Реализация (файлы, строки)` | `Архитектурный анализ и дефицит`.
- Отразить фактическую реализацию ранее отсутствовавших модулей:
  * Вложения файлов 10 форматов (R08) — `backend/app/files.py`, `backend/app/main.py`, тесты `backend/tests/test_attachments.py`.
  * Генерация отчетов XLSX/PDF/JSON (R10) — `backend/app/reports_export.py`, stdlib-генераторы, санитизация формул.
  * Интеграционные адаптеры LMS/Laravel (R12, R13) — `backend/app/integrations/*`, дедупликация `uq_inbox_dedup`.
  * Нагрузочные испытания (R18, R19) — результаты параллельных тестов и бенчмарков.
  * Workflow-миграции и версионирование (R06) — `backend/app/workflow.py`, `backend/app/services.py`.
  * Учебная аналитика и факты потоков (R30).

### R3. Детальный структурированный разбор разрывов по 8 доменам
Обобщить выводы доменных отчетов с указанием рисков и Ponytail-обоснований:
1. **Domain 01 (Модель данных):** Сущности, плоский `team_id` без FK, отсутствие `teams`, материализация `state_visits` vs `visit_id`, frozen dataset отчетов.
2. **Domain 02 (Workflow, FSM и миграции):** CAS revision, 15 состояний воронки, валидация атрибутов при переходах, версионирование и миграции v1->v2, UI-отрисовка альтернативных переходов.
3. **Domain 03 (Jobs, файлы и отчеты):** 10 форматов, magic bytes, SHA-256, stdlib xlsx/pdf, санитизация CSV-формул, синхронный пул AnyIO vs Celery.
4. **Domain 04 (Интеграции LMS и Laravel):** Контракты `SourceAdapter` / `CanonicalEnvelope`, дедупликация `uq_inbox_dedup`, курсоры чекпоинтов, mock vs live сетевые клиенты.
5. **Domain 05 (Безопасность, Auth, RBAC, 152-ФЗ, ФСТЭК №117):** Keycloak OIDC, RS256 JWKS, in-memory JWT, dynamic `scope_clause`, 404 изоляция данных, журнал аудита.
6. **Domain 06 (Фронтенд, UX и Rostelecom Gen2):** React SPA, 3 runtime deps, zero-reload, палитра Rostelecom Light, WCAG-контрастность, сохранение черновиков и фильтров.
7. **Domain 07 (Производительность, нагрузка и SLA):** Дефект лимитера AnyIO (40 vs 120 токенов), задержки <1с, конкурентный стресс 50 сессий + 10 отчетов, емкость пулов БД.
8. **Domain 08 (Инфраструктура, Docker, Non-Root, Секреты):** Non-root `appuser:10001`/`nginx:101`, fail-fast `${VAR:?error}`, loopback ports, DAG `service_healthy`, CSP HTTPS gap, Nginx 25m boundary error, Alembic vs create_all.

### R4. Сводный реестр архитектурного долга (Architectural Debt Ledger)
Сформировать единый реестр всех осознанных упрощений и отложенных задач с явной разметкой по этапам жизненного цикла:
- **Gate D (Демонстрация / Защита хакатона):** обоснованные упрощения по Ponytail Ladder, не блокирующие победу.
- **Gate P (Опытно-промышленный пилот):** задачи подготовки к пилотному внедрению.
- **Gate O (Промышленная эксплуатация):** архитектурные решения высокой доступности и масштабирования.

### R5. Сводный реестр критических исправлений (P0 Action List)
Выделить исчерпывающий перечень обязательных исправлений P0 перед финальной защитой:
1. Выставление AnyIO thread limiter `total_tokens = 120` в `backend/app/main.py`.
2. Добавление `https:` и `wss:` в CSP заголовок `deploy/nginx.conf`.
3. Устранение коллизии 25 МБ в Nginx (`client_max_body_size 26m`) и адаптация `verify_infra.py`.
4. Защита кода от записи в контейнере бэкенда (`COPY app ./app` в `backend/Dockerfile`).
5. Поддержка `Idempotency-Key` и CAS при загрузке файлов (`/attachments`).
6. Таблица `teams` и внешний ключ для командной изоляции.

### R6. Инварианты, форматы и сдача
- **Категорический запрет на модификацию архитектуры:** файлы `docs/architecture/*` строго READ-ONLY (`git diff docs/architecture` строго пуст).
- Исходный код `backend/`, `frontend/` и инфраструктура не модифицируются.
- Итоговый мастер-документ записывается в `docs/planning/07-gap-analysis.md`.
- Дубликат отчета сохраняется в `.agents/gap_aggregator/handoff.md`.
- Побайтовая идентичность (`sha256sum`) обоих файлов обязательна.

---

## Acceptance Criteria

### Полнота охвата и глубина сведения
- [ ] Документ `docs/planning/07-gap-analysis.md` содержит все 5 обязательных разделов (Executive Summary, Матрица R01–R30, Анализ 8 доменов, Debt Ledger, P0 Action List).
- [ ] Все требования R01–R30 детально сопоставлены с реальным кодом (файлы и строки) с устранением неактуальных пометок от 19 сентября.
- [ ] Факты и оценки строго совпадают с выводами из 8 отчетов `docs/planning/audit/domain-01` .. `domain-08`.
- [ ] Каждое отложенное решение классифицировано по гейтам (Gate D / Gate P / Gate O) с обоснованием по Ponytail Ladder.
- [ ] Сформирован точный перечень P0 исправлений с указанием конкретных файлов и строк для фикса.

### Целостность артефактов и инвариантов
- [ ] Созданы файлы `docs/planning/07-gap-analysis.md` и `.agents/gap_aggregator/handoff.md`.
- [ ] Хэши `sha256sum` обоих файлов совпадают на 100%.
- [ ] Каталог `docs/architecture/` не имеет изменений (`git status docs/architecture` чист).

## 2026-09-22T11:45:41Z

Сформировать детальный инженерный план доработок `docs/planning/audit/action-plan.md` на основе мастер Gap-анализа (`07-gap-analysis.md`), дорожной карты разработки (`04-two-developer-roadmap.md`), 8 доменных отчетов и правил Ponytail Ladder с разделением по горизонтам Gate D, Gate P и Gate O.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Блок Gate D (Хакатон / Демо-показ — Первоочередные инженерные задачи P0)
Детально специфицировать 6 критических задач P0 с соблюдением 4 предостережений ревьюеров (Adversarial Advisories):
1. **TASK-D01 (AnyIO Limiter & QueuePool Synchronization):**
   - Увеличение `total_tokens = 120` в `backend/app/main.py`.
   - Синхронное расширение `QueuePool` в `backend/app/db.py`: `pool_size=30, max_overflow=90` (суммарно 120) для предотвращения QueuePool Starvation при параллельной нагрузке 50 польз. + 10 отчетов (Advisory 1).
2. **TASK-D02 (Nginx CSP for Keycloak HTTPS):**
   - Добавление `https:` и `wss:` в директиву `connect-src` заголовка CSP в `deploy/nginx.conf` для работы OIDC в HTTPS.
3. **TASK-D03 (Nginx 26m Body Size & CI Oracle Atomic Alignment):**
   - Увеличение `client_max_body_size 26m;` в `deploy/nginx.conf` (компенсация multipart boundary ~300 байт при загрузке файлов ровно 25.0 МБ).
   - Атомарное обновление оракула `docs/checks/verify_infra.py:68` (`nginx_bytes in (25m, 26m)`), предотвращающее ложное падение CI (Advisory 4).
4. **TASK-D04 (Backend Dockerfile Non-Root Code Protection):**
   - Замена `COPY --chown=appuser:appuser app ./app` на `COPY app ./app` в `backend/Dockerfile` (код принадлежит root, рантайм read-only, запись только в `/app/storage` по CIS Docker Benchmark).
5. **TASK-D05 (Attachments Idempotency & CAS with UI Sync):**
   - Бэкенд: добавление `expected_revision: int | None = Form(None)` и заголовка `Idempotency-Key` в эндпоинт `POST /interactions/{id}/attachments` (`main.py`, `files.py`).
   - Фронтенд: синхронная передача `formData.append('expected_revision', String(item.revision))` в `frontend/src/views/InteractionPage.tsx` для предотвращения отказа загрузки файлов HTTP 422 (Advisory 2).
6. **TASK-D06 (Teams Table & Pre-Seeded Integrity):**
   - Создание модели `Team` и внешнего ключа `team_id` в `backend/app/models.py`.
   - Pre-seeding: создание записей `team-alpha` и `team-beta` в `backend/app/seed.py` и тестовых фикстурах `db_session` ДО создания пользователей и взаимодействий для исключения `IntegrityError` (Advisory 3).

Для каждой задачи TASK-D01..TASK-D06 указать:
- Идентификатор задачи (`TASK-D0X`).
- Ответственная зона: Разработчик А / Разработчик Б по `04-two-developer-roadmap.md`.
- Оценка трудоемкости (минуты / часы).
- Затрагиваемые файлы и точные номера строк.
- Готовый фрагмент кода (diff/patch block).
- Точные инструкции по верификации (запуск теста, проверка оракула, curl).

### R2. Блок Gate P (Опытно-промышленный пилот — Задачи P1)
Сформировать инженерные спецификации перехода от прототипа к пилоту:
- Замена `create_all` на версионированные миграции Alembic и выделенный контейнер/Job `db-migrator`.
- Реализация Live HTTP-клиентов к LMS Zion и сайту на Laravel на базе `httpx`.
- Сетевая сегментация Docker Compose (`frontend_net` и изолированная `db_net internal: true`).
- Включение Gzip-сжатия и генерации/проксирования `X-Request-ID` в Nginx.
- Добавление модели контактов вуза `OrganizationContact`.

### R3. Блок Gate O (Промышленная эксплуатация / Масштабирование — Задачи P2)
Специфицировать задачи перехода к высоконагруженному промышленному контуру:
- Разделение процессов API и воркеров: внедрение брокера Redis и распределенных воркеров Celery/RQ.
- Глобальная эпоха политик прав `access_policy_state.epoch` (`authz_epoch`) для инвалидации кэшей в распределенных узлах.
- Нормализация темпоральных фактов (`interaction_state_fact`, `state_visit`, `report_run`, `report_row`).
- Подключение антивирусного сканера ClamAV через потоковый сокет clamd.

### R4. Матрица ответственности и очередность исполнения
- Распределение задач между Разработчиком А (Backend Core, Infra, DB, Security) и Разработчиком Б (Frontend, Reports, Imports) в соответствии с `04-two-developer-roadmap.md`.
- Определение оптимальной последовательности применения фиксов Gate D для исключения конфликтов и регрессий.

### R5. Инварианты, форматы и сдача
- **Категорический запрет на модификацию архитектуры:** каталог `docs/architecture/*` строго READ-ONLY (`git diff docs/architecture` строго пуст).
- Исходный код `backend/`, `frontend/` и манифесты инфраструктуры не модифицируются в ходе планирования.
- Итоговый документ записывается в `docs/planning/audit/action-plan.md`.
- Дубликат отчета сохраняется в `.agents/action_plan_prioritizer/handoff.md`.
- Побайтовая идентичность (`sha256sum`) обоих файлов обязательна.

---

## Acceptance Criteria

### Полнота и точность инженерного плана
- [ ] Документ `docs/planning/audit/action-plan.md` содержит все 3 горизонта (Gate D, Gate P, Gate O).
- [ ] Задачи TASK-D01–TASK-D06 содержат полные спецификации, готовые diff-блоки, назначение Dev A / Dev B, оценки трудозатрат и проверочные команды.
- [ ] Все 4 Adversarial Advisories строго учтены в решениях задач блока Gate D.
- [ ] Задачи Gate P и Gate O декомпозированы с описанием архитектурных изменений.
- [ ] Матрица ответственности строго согласуется с `docs/architecture/04-two-developer-roadmap.md`.

### Целостность артефактов и инвариантов
- [ ] Созданы файлы `docs/planning/audit/action-plan.md` и `.agents/action_plan_prioritizer/handoff.md`.
- [ ] Хэши `sha256sum` обоих файлов совпадают на 100%.
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` без изменений).

## 2026-09-22T12:27:40Z

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-D01: синхронизировать лимитер пула рабочих потоков AnyIO (`total_tokens = 120`) в `backend/app/main.py` и пул соединений SQLAlchemy (`pool_size=30, max_overflow=90` — суммарно 120 соединений) в `backend/app/db.py` в строгом соответствии с принципами Ponytail Ladder и предостережением Adversarial Advisory 1.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Настройка лимитера AnyIO в `backend/app/main.py`
В контекстном менеджере `lifespan` перед `yield` настроить дефолтный лимитер рабочих потоков AnyIO на 120 токенов:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    import anyio.to_thread
    anyio.to_thread.current_default_thread_limiter().total_tokens = 120
    yield
```

### R2. Синхронное расширение QueuePool в `backend/app/db.py` (Adversarial Advisory 1)
В функции `get_engine()` настроить параметры пула соединений для предотвращения starvation:
- Для SQLite (не `:memory:`):
  * `connect_args["timeout"] = 30`
  * `options["pool_size"] = 30`
  * `options["max_overflow"] = 90`
  * `options["pool_timeout"] = 30`
  * PRAGMA прагмы в `sqlite_options`: `PRAGMA busy_timeout=30000`, `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`.
- Для PostgreSQL (`else`):
  * `options["pool_size"] = 30`
  * `options["max_overflow"] = 90`
  * `options["pool_timeout"] = 30`
- Сохранить `options["pool_pre_ping"] = True` и `StaticPool` для `:memory:`.

### R3. Сохранение архитектурных инвариантов и целостности
- Каталог `docs/architecture/*` строго READ-ONLY (`git diff docs/architecture` строго пуст).
- Никаких изменений в неотносящихся файлах.
- Минимальный diff по лестнице Ponytail.
- Отсутствие регрессий в API и существующих тестах.

---

## Acceptance Criteria

### Функциональная корректность и синхронизация
- [ ] В `backend/app/main.py` лимитер AnyIO инициализируется со значением 120.
- [ ] В `backend/app/db.py` параметры `pool_size=30`, `max_overflow=90` (суммарно 120) заданы для файлового SQLite и PostgreSQL.
- [ ] Прагмы `WAL`, `busy_timeout=30000` и `synchronous=NORMAL` установлены для SQLite-соединений.

### Тестирование и верификация
- [ ] Проверка инициализации: `python3 -c "from app.main import create_app; from app.db import get_engine; app = create_app(); print('App and Engine OK')"` завершается без ошибок.
- [ ] Тесты среза: `./backend/.venv/bin/pytest backend/tests/test_working_slice.py` проходят (17/17 passed).
- [ ] Полный набор тестов: `./backend/.venv/bin/pytest backend/tests/` проходит без регрессий (184/184 passed).
- [ ] Оракулы проверок: `python3 docs/checks/verify_infra.py` и `python3 docs/checks/verify_reports.py` завершаются с PASS.
- [ ] Каталог `docs/architecture/` не содержит изменений (`git status docs/architecture` чист).

## 2026-09-22T13:25:00Z

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-D02: добавить `https:` и `wss:` в директиву `connect-src` заголовка Content-Security-Policy в `deploy/nginx.conf` для поддержки работы OIDC Keycloak через защищенный протокол (HTTPS) в строгом соответствии с принципами Ponytail Ladder.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Обновление CSP-заголовка в `deploy/nginx.conf`
На строке 30 в директиве `add_header Content-Security-Policy` обновить список разрешенных протоколов в `connect-src`, добавив `https:` и `wss:`:
```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http: https: ws: wss:;" always;
```

### R2. Сохранение инвариантов и остальных настроек безопасности
- Каталог `docs/architecture/*` строго READ-ONLY (`git diff docs/architecture` строго пуст).
- Все остальные директивы безопасности Nginx (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `client_max_body_size`) остаются неизменными.
- Никаких изменений в неотносящихся файлах.
- Минимальный diff (1 строка).

---

## Acceptance Criteria

### Функциональная корректность
- [ ] В `deploy/nginx.conf` в заголовке CSP в `connect-src` присутствуют `https:` и `wss:`.
- [ ] Директивы 'self', `http:`, `ws:` сохранены.

### Верификация
- [ ] Оракул инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Тесты рабочего среза: `./backend/.venv/bin/pytest backend/tests/test_working_slice.py` проходят (17/17 passed).
- [ ] Все тесты: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий.
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).

## 2026-09-22T14:13:43Z

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-D03: увеличить `client_max_body_size` до `26m` в `deploy/nginx.conf` для устранения коллизии протокола multipart/form-data (~300 байт оверхеда на файлы ровно 25.0 МБ) и атомарно адаптировать проверочный оракул `docs/checks/verify_infra.py` в строгом соответствии с принципами Ponytail Ladder и предостережением Adversarial Advisory 4.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Обновление лимита в `deploy/nginx.conf`
В файле `deploy/nginx.conf` на строке 26 изменить значение директивы:
```nginx
client_max_body_size 26m;
```

### R2. Атомарная адаптация оракула `docs/checks/verify_infra.py` (Adversarial Advisory 4)
В функции `check_nginx_and_consistency()`:
- Строка 68: разрешить значения `25m` и `26m`:
  ```python
  require(nginx_bytes in (25 * 1024 * 1024, 26 * 1024 * 1024), f"nginx client_max_body_size must be 25m or 26m, got {val}{unit}")
  ```
- Строка 77: заменить проверку строгого равенства на нестрогое неравенство для поддержки буфера multipart-границ:
  ```python
  require(nginx_bytes >= backend_bytes,
          f"Nginx body limit ({nginx_bytes}) must be >= backend MAX_FILE_SIZE ({backend_bytes})")
  ```

### R3. Сохранение инвариантов и архитектурных границ
- Каталог `docs/architecture/*` строго READ-ONLY (`git diff docs/architecture` строго пуст).
- Все остальные проверки оракула (compose, dockerfiles, healthchecks, secrets) остаются нетронутыми.
- Атомарное внесение изменений (оба файла модифицируются совместно).

---

## Acceptance Criteria

### Функциональная корректность и синхронизация
- [ ] В `deploy/nginx.conf` задан лимит `client_max_body_size 26m;`.
- [ ] В `docs/checks/verify_infra.py` валидируется `nginx_bytes in (25m, 26m)` и `nginx_bytes >= backend_bytes`.

### Верификация
- [ ] Оракул инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Тесты рабочего среза: `./backend/.venv/bin/pytest backend/tests/test_working_slice.py` проходят (17/17 passed).
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (190/190 passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).


## Follow-up — 2026-09-22T15:01:01Z

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-D04: в `backend/Dockerfile` заменить инструкцию `COPY --chown=appuser:appuser app ./app` на `COPY app ./app` для защиты исполняемого кода приложения от модификации непривилегированным пользователем рантайма в соответствии с требованиями CIS Docker Benchmark (v1.6.0) и принципами Ponytail Ladder.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Защита исполняемого кода в `backend/Dockerfile`
В файле `backend/Dockerfile` на строке 12 убрать избыточную передачу прав владения кодом пользователю `appuser`:
```dockerfile
COPY app ./app
```
Файлы приложения должны принадлежать `root:root` (read-only в рантайме), а права на запись остаются исключительно у каталога `/app/storage` (настроенного на строках 10–11).

### R2. Сохранение инвариантов и остальных настроек безопасности
- Каталог `docs/architecture/*` строго READ-ONLY (`git diff docs/architecture` строго пуст).
- Все остальные директивы `backend/Dockerfile` (создание пользователя `appuser:10001`, права на `/app/storage`, директива `USER appuser`) остаются неизменными.
- Никаких изменений в неотносящихся файлах.
- Минимальный diff (1 строка).

---

## Acceptance Criteria

### Функциональная корректность
- [ ] В `backend/Dockerfile` инструкция копирования кода имеет вид `COPY app ./app`.
- [ ] Инструкции создания `appuser:10001`, `mkdir -p /app/storage`, `chown -R appuser:appuser /app/storage` и `USER appuser` сохранены.

### Верификация
- [ ] Оракул инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Тесты рабочего среза: `./backend/.venv/bin/pytest backend/tests/test_working_slice.py` проходят (17/17 passed).
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (190/190 passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).

## Follow-up — 2026-09-22T15:46:57Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

Реализовать задачу TASK-D05: синхронизировать загрузку вложений на фронтенде и бэкенде с поддержкой оптимистической блокировки (`cas`), идемпотентности (`Idempotency-Key`) и опциональной передачи `expected_revision` через `FormData`, предотвращая гонки `sequence` в `InteractionEvent` и сохраняя полную обратную совместимость с существующими клиентами.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Frontend UI Revision Synchronization (`frontend/src/views/InteractionPage.tsx`)
В функции `handleUploadAttachment` (строки 297–301) передавать текущую ревизию карточки в объекте `FormData`, если `item?.revision !== undefined`:
```typescript
const formData = new FormData();
formData.append('file', file);
if (item?.revision !== undefined) {
  formData.append('expected_revision', String(item.revision));
}
await api.upload('/interactions/' + encodeURIComponent(id) + '/attachments', formData, makeMutationKey());
```

### R2. Backend Extraction of File & Revision (`backend/app/main.py`)
Обеспечить извлечение опционального поля `expected_revision` из multipart-формы (`part.get_param("name", header="content-disposition") == "expected_revision"`) и из query-параметров / заголовков (`expected_revision`), сохранив полную обратную совместимость существующей функции `_extract_uploaded_file(request)` для других вызовов (например, импорта организаций).

### R3. Backend Idempotency & CAS Locking in `upload_attachment` (`backend/app/main.py`)
В эндпоинте `POST /api/v1/interactions/{interaction_id}/attachments`:
1. Принимать опциональный заголовок `idempotency_key: str | None = Header(None, alias="Idempotency-Key")`.
2. Извлекать `exp_rev` и при его наличии вызывать `cas(db, item, exp_rev)` для защиты от коллизий последовательностей журнала `InteractionEvent`.
3. При наличии `idempotency_key` использовать существующие функции `begin_command` и `finish_command` из `backend/app/services.py`.
4. Если `idempotency_key` не передан, сохранять файл и фиксировать транзакцию стандартно (`db.commit()`), гарантируя обратную совместимость со старыми клиентами и автотестами.

### R4. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (`git diff docs/architecture` строго пуст).
2. Никаких изменений в неотносящихся файлах.
3. Принцип Ponytail Ladder: минимальный рабочий diff, переиспользование существующих хелперов `cas`, `begin_command`, `finish_command` из `services.py`.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] В `frontend/src/views/InteractionPage.tsx` ревизия `expected_revision` передаётся в `FormData`, если `item?.revision !== undefined`.
- [ ] Сборка фронтенда: `cd frontend && pnpm build` проходит без ошибок.
- [ ] В `backend/app/main.py` эндпоинт `upload_attachment` поддерживает `Idempotency-Key` и `cas` при наличии `expected_revision`.
- [ ] Обратная совместимость: запросы без `expected_revision` и без `Idempotency-Key` продолжают успешно загружать файлы.
- [ ] Повторный запрос с тем же `Idempotency-Key` возвращает сохранённый ответ без повторного создания файла и дублирования событий.
- [ ] Попытка загрузки файла с устаревшей ревизией `expected_revision` возвращает ошибку `HTTP 409 REVISION_CONFLICT`.

### Верификация
- [ ] Тесты файловой подсистемы: `./backend/.venv/bin/pytest backend/tests/test_attachments.py` проходят успешно.
- [ ] Добавлены автоматические тесты для проверки `Idempotency-Key` и CAS-блокировки на эндпоинте вложений.
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (190+ passed).
- [ ] Оракул инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).



## Follow-up — 2026-09-22T17:28:07Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-D06: создать модель `Team` и добавить внешний ключ `ForeignKey("teams.id", ondelete="SET NULL")` для полей `team_id` в таблицах `users` и `interactions` (`backend/app/models.py`), а также обеспечить pre-seeding команд (`north`, `south`, `team-alpha`, `team-beta`) в `backend/app/seed.py` строго перед созданием пользователей для безупречного соблюдения ссылочной целостности SQLite `PRAGMA foreign_keys=ON` и изоляции прав руководителей по 152-ФЗ.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Модель данных `Team` и реляционные связи (`backend/app/models.py`)
1. Создать класс `Team(Base)` перед классом `User`:
   ```python
   class Team(Base):
       __tablename__ = "teams"
       id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
       name: Mapped[str] = mapped_column(String(200), nullable=False)
       created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
   ```
2. В классе `User` обновить поле `team_id`:
   ```python
   team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
   ```
3. В классе `Interaction` обновить поле `team_id`:
   ```python
   team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.id", ondelete="SET NULL"), index=True, nullable=True)
   ```

### R2. Pre-seeding команд перед созданием пользователей (`backend/app/seed.py`)
1. Импортировать модель `Team` в `backend/app/seed.py`.
2. В функции `seed_database(db: Session)` строго ДО создания направлений, программ и пользователей `USERS` выполнить создание базовых команд:
   ```python
   teams = {
       "north": "Команда Север",
       "south": "Команда Юг",
       "team-alpha": "Команда Альфа",
       "team-beta": "Команда Бета",
   }
   for ident, name in teams.items():
       _get_or_add(db, Team, ident, name=name)
   db.flush()
   ```

### R3. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Сохранение полной работоспособности всех существующих тестов при включенном `PRAGMA foreign_keys=ON`.
3. Принцип Ponytail Ladder: минимальный точечный diff без избыточных абстракций.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] Таблица `teams` создается при вызове `Base.metadata.create_all()`.
- [ ] Поле `User.team_id` ссылается на `teams.id` с поведением `ondelete="SET NULL"`.
- [ ] Поле `Interaction.team_id` ссылается на `teams.id` с поведением `ondelete="SET NULL"`.
- [ ] В `backend/app/seed.py` команды `north`, `south`, `team-alpha`, `team-beta` создаются до создания пользователей и взаимодействий.
- [ ] Попытка создать пользователя или взаимодействие с несуществующим `team_id` при включенных foreign keys вызывает ошибку целостности `IntegrityError`.

### Верификация
- [ ] Инициализация базы данных и сидинг: `python3 -m app.seed --init-db` и сидинг выполняются успешно без ошибок внешних ключей.
- [ ] Тесты безопасности и изоляции: `./backend/.venv/bin/pytest backend/tests/test_adversarial_security_invariants.py` проходят успешно (включая `test_cross_team_supervisor_isolation`).
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (208+ passed).
- [ ] Оракул инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).

## Follow-up — 2026-09-22T21:25:24Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-P01: внедрить версионированные миграции схемы базы данных на базе Alembic (`backend/alembic/`), сгенерировать базовую ревизию `0001_initial_schema.py` с поддержкой обратимости (`upgrade()` и `downgrade()`), добавить `alembic` в `backend/requirements.txt`, и внедрить в `compose.yaml` одноразовый сервис `db-migrator`, выполняющий накат миграций перед запуском основного API-сервиса, сохранив 100% совместимость с оракулом `verify_infra.py` и всеми тестами.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Добавление зависимости (`backend/requirements.txt`)
Добавить `alembic>=1.13,<2` в `backend/requirements.txt`.

### R2. Конфигурация Alembic (`backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`)
1. Создать `backend/alembic.ini` с указанием пути к каталогу миграций `alembic` и шаблона версий.
2. Создать `backend/alembic/env.py`, настроенный на чтение метаданных `Base.metadata` из `app.models` и динамическое получение `DATABASE_URL` из настроек приложения (`app.config.get_settings().database_url`) или переменной окружения `DATABASE_URL`.
3. Поддержать режим выполнения как онлайн (`run_migrations_online`), так и офлайн (`run_migrations_offline`), с корректной поддержкой PostgreSQL и SQLite.

### R3. Базовая миграция `0001_initial_schema.py` (`backend/alembic/versions/0001_initial_schema.py`)
1. Создать ревизию `0001_initial_schema`, воспроизводящую текущую реляционную схему всех таблиц:
   - `teams`, `users`, `organizations`, `organization_access`, `directions`, `programs`, `products`, `program_products`, `organization_contacts`, `contracts`, `licenses`, `interactions`, `attachments`, `comments`, `interaction_events`, `command_results`, `workflow_versions`, `workflow_migration_dry_runs`.
2. Реализовать симметричную функцию `downgrade()`, выполняющую корректный сброс таблиц в обратном порядке зависимостей.

### R4. Сервис `db-migrator` в `compose.yaml`
1. Добавить в `compose.yaml` сервис `db-migrator`:
   ```yaml
     db-migrator:
       build:
         context: ./backend
         dockerfile: Dockerfile
       environment:
         APP_ENV: development
         DATABASE_URL: postgresql+psycopg://rtk_crm:${CRM_DB_PASSWORD:?Set CRM_DB_PASSWORD in .env}@postgres:5432/rtk_crm
       command: ["alembic", "upgrade", "head"]
       depends_on:
         postgres:
           condition: service_healthy
       restart: "no"
   ```
2. В сервисе `api` добавить зависимость на успешное завершение мигратора:
   ```yaml
       depends_on:
         postgres:
           condition: service_healthy
         keycloak:
           condition: service_healthy
         db-migrator:
           condition: service_completed_successfully
   ```
3. Сохранить все существующие проверки `verify_infra.py` (наличие сервисов `postgres`, `keycloak`, `api`, `frontend`, условия `service_healthy`, volume `storage-data`).

### R5. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Полная обратная совместимость: существующие автотесты и запуск `Base.metadata.create_all()` / `app.seed` продолжают работать без регрессий.
3. Минимальный diff по принципам Ponytail Ladder.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] `backend/requirements.txt` содержит `alembic>=1.13,<2`.
- [ ] Файлы конфигурации `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako` созданы и валидны.
- [ ] Базовая миграция `backend/alembic/versions/0001_initial_schema.py` успешно применяется (`alembic upgrade head`) и откатывается (`alembic downgrade base`).
- [ ] В `compose.yaml` объявлен сервис `db-migrator`, а сервис `api` ожидает его успешного завершения (`condition: service_completed_successfully`).

### Верификация
- [ ] Тесты миграции: создан и проходит тест накатывания и отката миграций на SQLite и PostgreSQL (в `backend/tests/test_migrations.py`).
- [ ] Оракул инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (211+ passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).


## 2026-09-22T22:20:51Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-P02: разработать боевые сетевые HTTP-клиенты `LiveLMSAdapter` и `LiveWebsiteAdapter` на базе `httpx`/`urllib`, интегрировать их в фабрику адаптеров `get_adapter` (`backend/app/integrations/factory.py`), обеспечить таймауты (соединение 5с, чтение 30с), обработку сбоев сети и нормализацию данных в `NormalizedEnvelope`, сохранив 100% совместимость с mock-режимом и всеми тестами.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Сетевой клиент LMS Zion (`backend/app/integrations/live_lms.py`)
1. Создать класс `LiveLMSAdapter(BaseIntegrationAdapter)`:
   - Конструктор принимает `base_url: str`, `api_token: str | None = None`, `timeout: float = 10.0` (с таймаутами подключения 5.0с и чтения 30.0с).
   - Метод `health_check() -> dict[str, Any]`: выполняет GET-запрос к `{base_url}/api/v1/health`, замеряет `latency_ms` и возвращает словарь со статусом соединения (`status: "ok" | "error"`, `connected: bool`, `latency_ms: float`, `mode: "live"`, `source: "lms"`).
   - Метод `fetch_updates(since: datetime | None = None) -> list[NormalizedEnvelope]`:
     * Выполняет GET-запрос к `{base_url}/api/v1/metrics` (с опциональным query-параметром `since` в формате ISO-8601).
     * Передает заголовок `Authorization: Bearer <api_token>` при наличии токена.
     * Преобразует каждую метрику в `NormalizedEnvelope(source="lms", entity_type="learning_metric", external_id=..., payload=...)`.
     * Корректно перехватывает ошибки сети (Timeout, ConnectionError, HTTP 5xx) с логированием и безопасным возвратом (graceful degradation).

### R2. Сетевой клиент сайта на Laravel (`backend/app/integrations/live_website.py`)
1. Создать класс `LiveWebsiteAdapter(BaseIntegrationAdapter)`:
   - Конструктор принимает `base_url: str`, `api_token: str | None = None`, `timeout: float = 10.0`.
   - Метод `health_check() -> dict[str, Any]`: выполняет GET-запрос к `{base_url}/api/health`, замеряет задержку и возвращает статус подключения.
   - Метод `fetch_updates(since: datetime | None = None) -> list[NormalizedEnvelope]`:
     * Запрашивает `{base_url}/api/v1/applications` (партнерские заявки вузов).
     * Преобразует заявки в `NormalizedEnvelope(source="website", entity_type="application", external_id=..., payload=...)`.
     * Безопасно обрабатывает сетевые таймауты и сбои доступности.

### R3. Интеграция в фабрику (`backend/app/integrations/factory.py`)
В `get_adapter(source: str, settings: Settings | None = None)`:
- При `src == "lms"` и `mode == "live"` возвращать экземпляр `LiveLMSAdapter(base_url=cfg.lms_base_url)`.
- При `src == "website"` и `mode == "live"` возвращать экземпляр `LiveWebsiteAdapter(base_url=cfg.website_base_url)`.
- Сохранить инстанцирование `MockLMSAdapter` и `MockWebsiteAdapter` при `mode == "mock"`.

### R4. Тестовое покрытие (`backend/tests/test_live_integrations.py`)
Создать комплексный набор тестов для live-клиентов:
1. Успешный `health_check` и обработка недоступности удаленного сервиса (ConnectionRefused, Timeout, HTTP 500).
2. Успешный `fetch_updates` с корректной валидацией структуры `NormalizedEnvelope` (включая фильтрацию по `since` и передачу `Authorization`).
3. Фабрика `get_adapter`: проверка корректности возвращаемых адаптеров в режимах `mock` и `live`.
4. Обработка сетевых аномалий и сбоев (graceful degradation без падения вызывающего сервиса).

### R5. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Полная обратная совместимость: существующие тесты `test_integrations.py` и `test_adversarial_integrations.py` обязаны проходить на 100%.
3. Принцип Ponytail Ladder: минимальный, надежный код с переиспользованием `httpx` / `urllib`.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] Классы `LiveLMSAdapter` и `LiveWebsiteAdapter` реализованы и наследуются от `BaseIntegrationAdapter`.
- [ ] Фабрика `get_adapter` возвращает live-адаптеры при `lms_integration_mode == "live"` и `website_integration_mode == "live"`.
- [ ] Обработка сетевых ошибок (таймауты, недоступность хоста, 5xx) не приводит к сбою приложения.
- [ ] Метод `fetch_updates` возвращает валидные объекты `NormalizedEnvelope` с правильными `source`, `entity_type`, `external_id` и `payload`.

### Верификация
- [ ] Создан модуль тестов `backend/tests/test_live_integrations.py`, все тесты нового модуля проходят успешно.
- [ ] Существующие тесты интеграций `test_integrations.py` и `test_adversarial_integrations.py` проходят без регрессий.
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят (218+ passed).
- [ ] Оракул инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).


## 2026-09-23T11:18:54Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-P03: внедрить сегментацию сетей в `compose.yaml` (выделить внешнюю сеть `frontend_net` и изолированную внутреннюю сеть `backend_net` с `internal: true`), изолировать базу данных PostgreSQL, Keycloak и мигратор от прямого сетевого доступа веб-сервера Nginx, подключить сервис `api` в качестве защищённого шлюза к обеим сетям, сохранив 100% совместимость с оракулом `verify_infra.py` и всеми тестами.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Определение сегментированных сетей в `compose.yaml`
В файле `compose.yaml` добавить верхнеуровневую секцию `networks`:
```yaml
networks:
  frontend_net:
    driver: bridge
  backend_net:
    driver: bridge
    internal: true
```

### R2. Назначение сервисов по сегментам сетей
1. Сервис `frontend` подключить исключительно к `frontend_net`:
   ```yaml
   networks:
     - frontend_net
   ```
2. Сервисы СУБД, авторизации и миграций (`postgres`, `keycloak`, `db-migrator`) подключить исключительно к изолированной внутренней сети `backend_net`:
   ```yaml
   networks:
     - backend_net
   ```
3. Сервис `api` подключить к обеим сетям (`frontend_net` и `backend_net`), выполняя роль защищённого прикладного шлюза:
   ```yaml
   networks:
     - frontend_net
     - backend_net
   ```

### R3. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Все проверки оракула `docs/checks/verify_infra.py` (наличие всех 4 сервисов, healthchecks, зависимости `service_healthy`, том `storage-data`) обязаны оставаться в статусе PASS.
3. Все тесты бэкенда (`backend/tests/`) обязаны проходить без регрессий (269+ passed).
4. Принцип Ponytail Ladder: минимальный точечный diff в `compose.yaml` без усложнения инфраструктуры.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] В `compose.yaml` объявлены сети `frontend_net` и `backend_net` (с параметром `internal: true`).
- [ ] Сервис `frontend` присоединен исключительно к `frontend_net`.
- [ ] Сервисы `postgres`, `keycloak`, `db-migrator` присоединены исключительно к `backend_net`.
- [ ] Сервис `api` присоединен к обеим сетям (`frontend_net` и `backend_net`).
- [ ] Прямой сетевой доступ из веб-сервера к порту PostgreSQL физически исключен на уровне сетевой топологии.

### Верификация
- [ ] Проверка оракула инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (269+ passed).
- [ ] Синтаксис и топология `compose.yaml` валидны.
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).



## 2026-09-23T12:26:56Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-P04: включить сжатие gzip в `deploy/nginx.conf` (для json, js, css, text, xml, svg) и настроить сквозную трассировку `$request_id` через заголовок `X-Request-ID` на уровне обратного прокси Nginx, сохранив 100% совместимость с оракулом `verify_infra.py` и всеми тестами.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Включение сжатия Gzip в `deploy/nginx.conf`
В секции `http` (перед блоком `server`) включить конфигурацию `gzip`:
```nginx
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;
```

### R2. Настройка сквозной трассировки `X-Request-ID`
1. В секции `server` настроить выдачу заголовка клиенту:
   ```nginx
   add_header X-Request-ID $request_id always;
   ```
2. В секциях обратного проксирования передавать заголовок на бэкенд FastAPI:
   - В `location /api/`:
     ```nginx
     proxy_set_header X-Request-ID $request_id;
     ```
   - В `location ~ ^/(docs|redoc|openapi\.json|health)(/|$)`:
     ```nginx
     proxy_set_header X-Request-ID $request_id;
     ```

### R3. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Все проверки оракула `docs/checks/verify_infra.py` (лимит 26m, заголовок CSP с директивами `connect-src` и другие security headers) обязаны оставаться в статусе PASS.
3. Все тесты бэкенда (`backend/tests/`) обязаны проходить без регрессий (269+ passed).
4. Принцип Ponytail Ladder: минимальный точечный diff в `deploy/nginx.conf` без сторонних модулей и без изменения существующей схемы маршрутизации.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] В блоке `http` файла `deploy/nginx.conf` включен `gzip` с уровнем компрессии 6, минимальной длиной 1024 и указанными MIME-типами.
- [ ] В блоке `server` файла `deploy/nginx.conf` добавлена директива `add_header X-Request-ID $request_id always;`.
- [ ] В блоках `location /api/` и `location ~ ^/(docs|redoc|openapi\.json|health)(/|$)` настроена передача `proxy_set_header X-Request-ID $request_id;`.
- [ ] Синтаксис Nginx корректен.

### Верификация
- [ ] Проверка оракула инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (269+ passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист).


## 2026-09-23T13:42:04Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-P05: нормализовать модель контактов образовательных организаций OrganizationContact в `backend/app/models.py` (расширить email до 320 символов согласно стандарту RFC 5321, добавить поля notes, revision, created_at, updated_at, archived_at и составной индекс `ix_org_contacts_active`), создать новую обратимую ревизию миграции Alembic `backend/alembic/versions/0002_normalize_contacts.py` с полной поддержкой upgrade() и downgrade(), адаптировать тесты миграций `backend/tests/test_migrations.py` к новой ревизии head, обеспечив нулевой дрейф схемы (`alembic check`) и 100% обратную совместимость всех 269 существующих автотестов.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Нормализация модели `OrganizationContact` в `backend/app/models.py`
В объявлении класса `OrganizationContact`:
1. Расширить длину поля `email` до 320 символов (`String(320)` по стандарту RFC 5321).
2. Добавить поля аудита, заметок и версионирования:
   - `notes: Mapped[str | None] = mapped_column(Text, nullable=True)`
   - `revision: Mapped[int] = mapped_column(Integer, default=1)`
   - `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)`
   - `updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)`
   - `archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)`
3. Добавить составной индекс для быстрого поиска активных контактов организации:
   ```python
   __table_args__ = (
       Index("ix_org_contacts_active", "organization_id", "archived_at"),
   )
   ```

### R2. Ревизия миграции Alembic `0002_normalize_contacts.py`
Создать файл `backend/alembic/versions/0002_normalize_contacts.py`:
- Идентификаторы: `revision = "0002_normalize_contacts"`, `down_revision = "0001_initial_schema"`.
- `upgrade()`:
  - Использовать `op.batch_alter_table("organization_contacts", schema=None)` для универсальной поддержки SQLite и PostgreSQL.
  - Расширить колонку `email` до `String(320)`.
  - Добавить колонки `notes` (Text, nullable), `revision` (Integer, default=1), `created_at` (DateTime(timezone=True), server_default CURRENT_TIMESTAMP), `updated_at` (DateTime(timezone=True), server_default CURRENT_TIMESTAMP), `archived_at` (DateTime(timezone=True), nullable).
  - Создать индекс `ix_org_contacts_active` по колонкам `["organization_id", "archived_at"]`.
- `downgrade()`:
  - Использовать `op.batch_alter_table("organization_contacts", schema=None)`.
  - Удалить индекс `ix_org_contacts_active`.
  - Удалить добавленные колонки (`archived_at`, `updated_at`, `created_at`, `revision`, `notes`).
  - Вернуть тип колонки `email` обратно к `String(200)`.

### R3. Адаптация и валидация тестов миграций
В `backend/tests/test_migrations.py`:
- Обновить проверку актуального head ревизии с `0001_initial_schema` на `0002_normalize_contacts`.
- Добавить проверку структуры обновленной таблицы `organization_contacts` (наличие полей `email`, `notes`, `revision`, `created_at`, `updated_at`, `archived_at` и индекса `ix_org_contacts_active`).
- Убедиться, что `alembic.command.check` проходит без исключений (zero schema drift между `Base.metadata` и миграциями).
- Добавить специализированные тесты для жизненного цикла нормализованных контактов (создание, обновление ревизии, архивирование через `archived_at`, фильтрация активных).

### R4. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Все проверки оракула `docs/checks/verify_infra.py` и функциональных оракулов обязаны оставаться в статусе PASS.
3. Все существующие тесты бэкенда (`backend/tests/`) обязаны проходить без регрессий (269+ passed).
4. Принцип Ponytail Ladder: минимальный точечный diff в `models.py` и изолированная ревизия миграции.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] В `backend/app/models.py` класс `OrganizationContact` содержит:
  - `email: Mapped[str | None] = mapped_column(String(320), nullable=True)`
  - `notes: Mapped[str | None] = mapped_column(Text, nullable=True)`
  - `revision: Mapped[int] = mapped_column(Integer, default=1)`
  - `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)`
  - `updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)`
  - `archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)`
  - `Index("ix_org_contacts_active", "organization_id", "archived_at")`
- [ ] Создана миграция `backend/alembic/versions/0002_normalize_contacts.py` с полной поддержкой `upgrade()` и `downgrade()` через `batch_alter_table`.
- [ ] `command.check()` в Alembic подтверждает отсутствие расхождений схемы (Zero Schema Drift).
- [ ] Применение `upgrade("head")` и откат `downgrade("base")` / `downgrade("-1")` работают без сбоев на SQLite и PostgreSQL.

### Верификация
- [ ] Проверка оракула инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (270+ passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист, 0 байт изменений).


## 2026-09-23T16:26:35Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-O02: внедрить глобальную эпоху политик доступа `access_policy_state.epoch` (`authz_epoch`) для защиты от исполнения фоновых и асинхронных операций на устаревшем контексте прав (152-ФЗ), создать синглтон-модель `AccessPolicyState`, служебные функции `get_authz_epoch` и `bump_authz_epoch` в `backend/app/services.py`, вызывать инкремент эпохи при мутациях прав доступа (смена владельца взаимодействия, обновление `OrganizationAccess`, смена ролей пользователей), создать ревизию миграции Alembic `backend/alembic/versions/0003_authz_epoch.py` с автоматической инициализацией синглтона, добавить тесты в `backend/tests/test_authz_epoch.py` и обеспечить нулевой дрейф схемы (`alembic check`) и 100% обратную совместимость всех 274 существующих тестов.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Модель данных `AccessPolicyState` в `backend/app/models.py`
Создать синглтон-модель `AccessPolicyState`:
```python
class AccessPolicyState(Base):
    __tablename__ = "access_policy_state"
    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

### R2. Сервисные функции `get_authz_epoch` и `bump_authz_epoch` в `backend/app/services.py`
1. Реализовать `get_authz_epoch(db: Session) -> int`:
   - Возвращает текущее значение `epoch` из записи `singleton_id=1`.
   - Если запись еще не создана, создает запись с `singleton_id=1, epoch=1` и возвращает 1.
2. Реализовать `bump_authz_epoch(db: Session) -> int`:
   - Атомарно инкрементирует `epoch` на 1 и обновляет `updated_at = utcnow()`.
   - Возвращает новое значение эпохи.
3. Интегрировать `bump_authz_epoch(db)` в места мутации прав доступа:
   - При переназначении владельца взаимодействия (`services.assign`).
   - При выдаче или изменении прав доступа к организациям (`OrganizationAccess`).
   - При любых изменениях ролей, команд или активности пользователей (`User.role`, `User.team_id`, `User.active`).

### R3. Ревизия миграции Alembic `0003_authz_epoch.py`
Создать файл `backend/alembic/versions/0003_authz_epoch.py`:
- Идентификаторы: `revision = "0003_authz_epoch"`, `down_revision = "0002_normalize_contacts"`.
- `upgrade()`:
  - Создает таблицу `access_policy_state` (`singleton_id: Integer primary key`, `epoch: Integer nullable=False server_default='1'`, `updated_at: DateTime(timezone=True) server_default=CURRENT_TIMESTAMP`).
  - Выполняет вставку начальной строки: `INSERT INTO access_policy_state (singleton_id, epoch) VALUES (1, 1)`.
- `downgrade()`:
  - Удаляет таблицу `access_policy_state`.

### R4. Набор тестов и адаптация миграций
1. Создать новый тестовый модуль `backend/tests/test_authz_epoch.py`:
   - Проверка инициализации синглтона и чтения эпохи через `get_authz_epoch`.
   - Проверка корректного инкремента при вызове `bump_authz_epoch`.
   - Проверка инкремента эпохи при вызове `assign()` (смена владельца взаимодействия).
   - Проверка инкремента эпохи при манипуляциях с `OrganizationAccess`.
   - Проверка изоляции прав (152-ФЗ) и детекции устаревшей эпохи авторизации.
2. Обновить `backend/tests/test_migrations.py`:
   - Добавить `"access_policy_state"` в `EXPECTED_TABLES`.
   - Обновить head ревизию на `0003_authz_epoch`.
   - Проверить, что `alembic.command.check` проходит без расхождений (Zero Schema Drift).

### R5. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Все проверки оракула `docs/checks/verify_infra.py` и функциональных оракулов обязаны оставаться в статусе PASS.
3. Все существующие тесты бэкенда (`backend/tests/`) обязаны проходить без регрессий (274+ passed).
4. Принцип Ponytail Ladder: минимальный точечный diff, синглтон-строка, стандартные транзакции БД.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] Таблица и модель `AccessPolicyState` определены в `backend/app/models.py`.
- [ ] Создана миграция `0003_authz_epoch.py` с зависимостью от `0002_normalize_contacts`, корректными `upgrade()` (с сидированием `singleton_id=1, epoch=1`) и `downgrade()`.
- [ ] Функции `get_authz_epoch` и `bump_authz_epoch` реализованы в `backend/app/services.py`.
- [ ] При мутациях прав доступа (смена ответственного, назначение прав организации) вызывается `bump_authz_epoch(db)`.
- [ ] `command.check()` в Alembic подтверждает отсутствие расхождений схемы (Zero Schema Drift).

### Верификация
- [ ] Проверка оракула инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Все тесты бэкенда, включая `test_authz_epoch.py`: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (274+ passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист, 0 байт изменений).

## 2026-09-23T19:03:08Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-O03: нормализация темпоральных таблиц фактов (StateVisit для материализации времени нахождения карточки на этапах и расчета SLA duration_seconds, ReportRun и ReportRow для фиксации замороженных срезов отчетов Frozen Datasets), создание ревизии миграции Alembic `backend/alembic/versions/0004_temporal_fact_tables.py` с нулевым дрейфом схемы, интеграция материализации визитов при переходах состояний в `backend/app/services.py`, добавление тестов в `backend/tests/test_temporal_facts.py` и сохранение 100% обратной совместимости всех существующих 292 тестов.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Модели данных `StateVisit`, `ReportRun`, `ReportRow` в `backend/app/models.py`
1. Модель `StateVisit`:
```python
class StateVisit(Base):
    __tablename__ = "state_visits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    interaction_id: Mapped[str] = mapped_column(ForeignKey("interactions.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
```
2. Модели `ReportRun` и `ReportRow`:
```python
class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    knowledge_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    dataset_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportRow(Base):
    __tablename__ = "report_rows"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    report_run_id: Mapped[str] = mapped_column(ForeignKey("report_runs.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    row_data: Mapped[dict] = mapped_column(JSON, default=dict)
```

### R2. Сервисная логика в `backend/app/services.py`
1. При создании взаимодействия (`create_interaction`) создавать начальный `StateVisit` с `state=item.state`, `entered_at=now`.
2. При переходе состояния (`transition`):
   - Находить текущий открытый `StateVisit` (`interaction_id == item.id, exited_at.is_(None)`).
   - Закрывать его: `exited_at = now`, `duration_seconds = max(0.0, (now - visit.entered_at).total_seconds())`.
   - Создавать новый открытый `StateVisit` для целевого статуса (`state=to_state, entered_at=now`).
3. Предоставить сервисные хелперы для замороженных датасетов:
   - `freeze_report_dataset(db: Session, user: User, report_type: str, parameters: dict, rows: list[dict], knowledge_cutoff: datetime | None = None) -> ReportRun`
   - `get_frozen_report_rows(db: Session, report_run_id: str) -> list[dict]`

### R3. Ревизия миграции Alembic `0004_temporal_fact_tables.py`
Создать файл `backend/alembic/versions/0004_temporal_fact_tables.py`:
- Идентификаторы: `revision = "0004_temporal_fact_tables"`, `down_revision = "0003_authz_epoch"`.
- `upgrade()`:
  - Создает таблицы `state_visits`, `report_runs`, `report_rows` с внешними ключами и индексами.
- `downgrade()`:
  - Удаляет таблицы в обратном порядке (`report_rows`, `report_runs`, `state_visits`).

### R4. Набор тестов и адаптация миграций
1. Создать тестовый модуль `backend/tests/test_temporal_facts.py`:
   - Тестирование фиксации `StateVisit` при создании взаимодействия и переходах.
   - Проверка расчета `duration_seconds` и временных меток входа/выхода.
   - Тестирование заморозки датасетов через `freeze_report_dataset` и чтения `get_frozen_report_rows`.
2. Обновить `backend/tests/test_migrations.py`:
   - Добавить `"state_visits"`, `"report_runs"`, `"report_rows"` в `EXPECTED_TABLES`.
   - Обновить head ревизию на `0004_temporal_fact_tables`.
   - Проверить, что `alembic.command.check` проходит без расхождений (Zero Schema Drift).

### R5. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Все проверки оракула `docs/checks/verify_infra.py` и функциональных оракулов (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) обязаны оставаться в статусе PASS.
3. Все существующие тесты бэкенда (`backend/tests/`) обязаны проходить без регрессий (292+ passed).
4. Принцип Ponytail Ladder: минимальный точечный diff, стандартные транзакции БД, отсутствие лишних слоев абстракции.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] Таблицы `StateVisit`, `ReportRun`, `ReportRow` определены в `backend/app/models.py`.
- [ ] Создана миграция `0004_temporal_fact_tables.py` с линейной зависимостью от `0003_authz_epoch`, валидными `upgrade()` и `downgrade()`.
- [ ] При создании и переходах взаимодействий материализуются визиты состояний `state_visits` с корректным вычислением `duration_seconds`.
- [ ] Доступны функции сохранения и чтения замороженных отчетов (`freeze_report_dataset`, `get_frozen_report_rows`).
- [ ] `command.check()` в Alembic подтверждает отсутствие расхождений схемы (Zero Schema Drift).

### Верификация
- [ ] Проверка оракула инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Все функциональные оракулы (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) завершаются со статусом PASS.
- [ ] Все тесты бэкенда, включая `test_temporal_facts.py`: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (292+ passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист, 0 байт изменений).



## 2026-09-23T20:03:37Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализовать задачу TASK-O04: потоковую антивирусную проверку загружаемых вложений через сетевой сокет демона ClamAV (`clamd`) по протоколу `INSTREAM` (порт 3310) на базе стандартной библиотеки Python (`socket`, `struct`) без внешних библиотек, добавить параметры конфигурации ClamAV в `backend/app/config.py`, встроить антивирусную проверку в `backend/app/files.py`, объявить сервис `clamav` в `compose.yaml` в сети `backend_net` с healthcheck-проверкой, написать комплексный набор тестов в `backend/tests/test_clamav.py` и обеспечить 100% обратную совместимость всех существующих 318 тестов и 4 оракулов.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Параметры конфигурации ClamAV в `backend/app/config.py`
В классе `Settings` и фабрике `get_settings()` добавить параметры:
- `clamav_host: str = "clamav"` (из переменной окружения `CLAMAV_HOST`)
- `clamav_port: int = 3310` (из переменной окружения `CLAMAV_PORT`)
- `clamav_enabled: bool = False` (из переменной окружения `CLAMAV_ENABLED`, флаг активации сетевой проверки)
- `clamav_timeout: float = 10.0` (из переменной окружения `CLAMAV_TIMEOUT`)

### R2. Реализация протокола `clamd INSTREAM` в `backend/app/files.py`
1. Реализовать функцию `scan_clamav_stream(data: bytes, host: str, port: int, timeout: float = 10.0) -> str | None`:
   - Подключение через стандартный сетевой сокет `socket.socket(socket.AF_INET, socket.SOCK_STREAM)` с таймаутом.
   - Отправка команды `zINSTREAM\0` (или `nINSTREAM\n`).
   - Потоковая передача данных чанками (размером до 64 КБ). Каждый чанк предваряется 4-байтным целым в big-endian (`struct.pack(">I", chunk_len)`), за которым следуют байты чанка.
   - Завершение передачи нулевым чанком `struct.pack(">I", 0)`.
   - Чтение ответа сокета:
     * Если ответ содержит `OK` — файл чист (возвращает `None`).
     * Если ответ содержит `FOUND` — извлекается имя вредоносной сигнатуры и возвращается строка сигнатуры.
     * Если ответ содержит `ERROR` — выбрасывается соответствующее исключение.
2. Встроить проверку в функцию `save_attachment`:
   - Если в настройках `clamav_enabled=True`, вызывать `scan_clamav_stream(file_bytes, ...)`.
   - При обнаружении угрозы выбрасывать стандартизированную ошибку:
     `APIError("VIRUS_DETECTED", f"Обнаружена вредоносная сигнатура: {virus_name}", 422)`.
   - Если `clamav_enabled=False`, сокет не вызывается, проверка ограничивается валидацией magic-bytes и размера.
   - При сбое подключения или сетевом таймауте сокета при `clamav_enabled=True` выбрасывать `APIError("ANTIVIRUS_UNAVAILABLE", "Сервис антивирусной проверки временно недоступен.", 503)`.

### R3. Конфигурация сервиса ClamAV в `compose.yaml`
1. В `compose.yaml` объявить сервис `clamav`:
   ```yaml
   clamav:
     image: clamav/clamav:latest
     networks:
       - backend_net
     healthcheck:
       test: ["CMD-SHELL", "echo PING | nc -w 1 127.0.0.1 3310 | grep -q PONG || exit 1"]
       interval: 10s
       timeout: 5s
       retries: 10
       start_period: 30s
     restart: unless-stopped
   ```
2. В сервисе `api` в секции `environment` объявить:
   ```yaml
   CLAMAV_HOST: ${CLAMAV_HOST:-clamav}
   CLAMAV_PORT: ${CLAMAV_PORT:-3310}
   CLAMAV_ENABLED: ${CLAMAV_ENABLED:-false}
   ```
3. Сохранить все существующие проверки оракула `docs/checks/verify_infra.py` (все 4 базовых сервиса, зависимости `service_healthy`, том `storage-data`).

### R4. Набор автотестов `backend/tests/test_clamav.py`
Создать тестовый модуль `backend/tests/test_clamav.py`:
- Тест чистого файла: mock-сервер ClamAV возвращает `stream: OK`, загрузка проходит успешно.
- Тест вируса (сигнатура EICAR): mock-сервер возвращает `stream: Eicar-Signature FOUND`, эндпоинт загрузки возвращает HTTP 422 `VIRUS_DETECTED`.
- Тест недоступности / таймаута сокета: при `CLAMAV_ENABLED=True` и недоступном сервере возвращается HTTP 503 `ANTIVIRUS_UNAVAILABLE`.
- Тест отключенного антивируса: при `CLAMAV_ENABLED=False` загрузка валидного файла проходит без обращения к сокету.
- Тест протокола INSTREAM: побайтовая проверка структуры фреймов `struct.pack(">I", length)` и завершающего нулевого чанка.

### R5. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Запрещено добавлять сторонние пакеты в `backend/requirements.txt` (Ponytail Ladder: только `stdlib`).
3. Все проверки оракула `docs/checks/verify_infra.py` и функциональных оракулов (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) обязаны оставаться в статусе PASS.
4. Все существующие тесты бэкенда (`backend/tests/`) обязаны проходить без регрессий (318+ passed).

---

## Acceptance Criteria

### Функциональная корректность
- [ ] Параметры `CLAMAV_*` добавлены в `Settings` в `backend/app/config.py`.
- [ ] Клиент `clamd INSTREAM` на чистом модуле `socket` реализован в `backend/app/files.py`.
- [ ] При обнаружении вируса загрузка блокируется с ошибкой HTTP 422 `VIRUS_DETECTED`.
- [ ] При `CLAMAV_ENABLED=False` поведение загрузки файлов сохраняет 100% обратную совместимость.
- [ ] Сервис `clamav` объявлен в `compose.yaml` в сети `backend_net` с healthcheck-проверкой.

### Верификация
- [ ] Проверка оракула инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Все функциональные оракулы (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) завершаются со статусом PASS.
- [ ] Все тесты бэкенда, включая `test_clamav.py`: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (318+ passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист, 0 байт изменений).


## 2026-09-23T21:31:32Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Зафиксировать успешное завершение TASK-O04 (ClamAV Instream Antivirus) в отчётах аудита и реализовать задачу TASK-O01: разделение процессов и асинхронные фоновые задачи (Process Decoupling — Redis, Background Jobs & Transactional Outbox) в соответствии со спецификацией `action-plan.md:478-505` и инвариантами 152-ФЗ. Создать модели `BackgroundJob` и `TransactionalOutbox`, миграцию Alembic `0005_background_jobs_and_outbox.py`, добавить сервис `redis` в `compose.yaml`, реализовать функции постановки и процессинга фоновых задач с валидацией `authz_epoch` (152-ФЗ) и эндпоинты `POST /api/v1/jobs/reports/snapshot` (HTTP 202 Accepted) и `GET /api/v1/jobs/{job_id}`, покрыть комплексными тестами в `backend/tests/test_background_jobs.py` с сохранением 100% обратной совместимости всех существующих 344 тестов и 4 оракулов.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Модели данных `BackgroundJob` и `TransactionalOutbox` в `backend/app/models.py`
1. Модель `BackgroundJob`:
```python
class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    authz_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```
2. Модель `TransactionalOutbox`:
```python
class TransactionalOutbox(Base):
    __tablename__ = "transactional_outbox"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### R2. Ревизия миграции Alembic `0005_background_jobs_and_outbox.py`
Создать файл `backend/alembic/versions/0005_background_jobs_and_outbox.py`:
- Идентификаторы: `revision = "0005_background_jobs_and_outbox"`, `down_revision = "0004_temporal_fact_tables"`.
- `upgrade()`:
  - Создает таблицы `background_jobs` и `transactional_outbox` с индексами и внешними ключами.
- `downgrade()`:
  - Удаляет таблицы в обратном порядке (`transactional_outbox`, `background_jobs`).
- Обновить `EXPECTED_TABLES` и актуальный head в `backend/tests/test_migrations.py`.

### R3. Инфраструктура в `compose.yaml` и `backend/app/config.py`
1. В `compose.yaml` объявить сервис `redis`:
   ```yaml
   redis:
     image: redis:7-alpine
     networks:
       - backend_net
     healthcheck:
       test: [CMD, redis-cli, ping]
       interval: 5s
       timeout: 3s
       retries: 5
     restart: unless-stopped
   ```
2. В сервисе `api` в секции `environment` добавить:
   ```yaml
   REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
   ```
3. В `backend/app/config.py` добавить настройки:
   - `redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")`
   - `background_worker_enabled: bool = False` (по умолчанию безопасный in-process / AnyIO фолбэк).

### R4. Сервисы и API (`backend/app/services.py` и `backend/app/main.py`)
1. В `services.py` реализовать:
   - `enqueue_background_job(db: Session, user: User, kind: str, parameters: dict) -> BackgroundJob`:
     Создает и сохраняет `BackgroundJob` со статусом `"queued"` и текущей эпохой `authz_epoch = get_authz_epoch(db)`.
   - `process_background_job(db: Session, job_id: str) -> BackgroundJob`:
     Берет задачу, переводит в `"running"`. Проверяет `check_authz_epoch(db, job.authz_epoch)`.
     Если права изменились, отменяет задачу: `status = "cancelled"`, `error_message = "REPORT_SCOPE_CHANGED"` (требование 152-ФЗ).
     Если права валидны, выполняет генерацию отчета, замораживает результат через `freeze_report_dataset`, сохраняет `result_id = report_run.id`, переводит в `status = "completed"`, `progress = 100`.
   - `get_background_job_scoped(db: Session, user: User, job_id: str) -> BackgroundJob`:
     Проверяет область видимости (152-ФЗ): обычный пользователь видит только свои задачи (`job.requester_id == user.id`), руководитель — задачи своей команды / свои, админ — задачи системы. Чужие задачи возвращают 404.
2. В `backend/app/main.py` добавить эндпоинты:
   - `POST /api/v1/jobs/reports/snapshot` -> статус HTTP 202 Accepted, тело `{"job_id": job.id, "status": "queued"}`.
   - `GET /api/v1/jobs/{job_id}` -> статус задачи, прогресс, `result_id`, `error_message`.

### R5. Набор тестов `backend/tests/test_background_jobs.py`
Создать тестовый модуль `backend/tests/test_background_jobs.py`:
- Тест полного жизненного цикла: `queued` -> `running` -> `completed` с получением `result_id`.
- Тест защиты по 152-ФЗ: вызов `bump_authz_epoch` во время ожидания задачи приводит к отмене с кодом `REPORT_SCOPE_CHANGED`.
- Тест изоляции видимости: попытка чтения чужой фоновой задачи возвращает HTTP 404 (не раскрывать существование).
- Тест API эндпоинтов: проверка `POST /api/v1/jobs/reports/snapshot` (HTTP 202) и поллинга через `GET /api/v1/jobs/{job_id}`.

### R6. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Запрещено добавлять сторонние пакеты в `backend/requirements.txt` (Ponytail Ladder: стандартные библиотеки и существующие зависимости).
3. Все проверки оракула `docs/checks/verify_infra.py` и функциональных оракулов (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) обязаны оставаться в статусе PASS.
4. Все существующие тесты бэкенда (`backend/tests/`) обязаны проходить без регрессий (344+ passed).
5. Нулевой дрейф схемы БД: `alembic check` подтверждает полное совпадение с `Base.metadata`.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] Модели `BackgroundJob` и `TransactionalOutbox` определены в `backend/app/models.py`.
- [ ] Создана миграция `0005_background_jobs_and_outbox.py` с зависимостью от `0004_temporal_fact_tables`, корректными `upgrade()` и `downgrade()`.
- [ ] Сервис `redis` добавлен в `compose.yaml` в сети `backend_net` с healthcheck.
- [ ] Реализованы сервисные функции `enqueue_background_job`, `process_background_job`, `get_background_job_scoped`.
- [ ] При смене эпохи прав (`bump_authz_epoch`) задача отменяется с ошибкой `REPORT_SCOPE_CHANGED` (152-ФЗ).
- [ ] Эндпоинты `POST /api/v1/jobs/reports/snapshot` и `GET /api/v1/jobs/{job_id}` реализованы в `main.py`.
- [ ] `command.check()` в Alembic подтверждает отсутствие расхождений схемы (Zero Schema Drift).

### Верификация
- [ ] Проверка оракула инфраструктуры: `python3 docs/checks/verify_infra.py` завершается со статусом PASS.
- [ ] Все функциональные оракулы (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) завершаются со статусом PASS.
- [ ] Все тесты бэкенда, включая `test_background_jobs.py`: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (344+ passed).
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист, 0 байт изменений).


## Follow-up — 2026-09-24T16:56:20Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

Устранение замечаний внешнего аудита F02–F12 (Архитектурная чистота и безопасность 152-ФЗ) в проекте rost_crm. Провести ревизию и последовательно реализовать исправления четырёх пакетов задач (F02–F12), обеспечить 100% прохождение всех тестов, нулевой дрейф схемы Alembic, сборку фронтенда и прохождение всех 4 системных оракулов при строгом соблюдении принципа Ponytail Ladder и неизменности `docs/architecture/`.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Пакет 1: Безопасность и разграничение доступа 152-ФЗ (F02, F03, F04)
1. **F02 (Миграция воркфлоу):**
   - В `backend/app/services.py` в функциях `preview_workflow_migration` и `commit_workflow_migration`:
     * Ограничить выборку мигрируемых карточек областью видимости пользователя через `scope_clause(user)`.
     * При миграции на этапы из `SUBJECT_REQUIRED_STATES` (включая `classes`) проверять предметную привязку `validate_subject(db, item.program_id, item.product_id)`. Если программа/продукт не заполнены — выбрасывать `APIError("VALIDATION_ERROR", ..., 422)` с детализацией невалидных карточек.
2. **F03 (Учебные показатели):**
   - В `backend/app/integrations/service.py` в функции `get_learning_metrics_summary`:
     * Применять фильтрацию `visible_organization_ids(db, user)` для всех ролей.
     * Если у пользователя нет доступа к запрашиваемой организации — возвращать нулевые агрегаты либо 404 (не раскрывать существование).
3. **F04 (Права на загрузку вложений):**
   - В `backend/app/main.py` в эндпоинте загрузки вложений `upload_attachment`:
     * Добавить проверку прав на запись взаимодействия: `require_permission(user, "interactions.write")`. Пользователь с правом только на чтение (`read_all=True`) обязан получать `403 FORBIDDEN`.

### R2. Пакет 2: Корректность отчётов и экспорт PDF (F05, F06, F10)
1. **F05 (Читаемый PDF):**
   - В `backend/app/reports_export.py`:
     * Исправить рендеринг кириллицы: встроить базовый Type0/CIDFont с Unicode-маппингом или кодовую страницу CP1251/WinAnsi с русскими глифами, обеспечив корректное отображение кириллицы в стандартных PDF-просмотрщиках.
     * Заменить жесткую обрезку ячеек до 22 символов на динамический расчет ширины колонок или перенос текста.
2. **F06 (Контракт отчёта Created):**
   - В `backend/app/services.py:created_report` вернуть в словарь `totals`: `"interactions": len(rows)`, `"organizations": len(counts_by_organization)`, `"counts_by_state": counts_by_state`.
   - В `frontend/src/views/Reports.tsx` добавить безопасный доступ к `createdResult.totals` с fallback-значениями.
3. **F10 (Согласованность выгрузок и активные этапы):**
   - В `frontend/src/views/Reports.tsx`:
     * Рассчитывать количество активных этапов только по ненулевым группам: `Object.values(countsByState).filter(c => c > 0).length`.
     * Связать кнопки экспорта с актуальным `report_run_id`, исключив рассинхронизацию между экраном и скачиваемым файлом.

### R3. Пакет 3: Импорт данных XLSX/CSV и права (F07, F08, F09)
1. **F07 (Парсер XLSX с учётом разреженных ячеек):**
   - В `backend/app/importer.py:parse_xlsx_stdlib`:
     * Извлекать буквенный индекс колонки из атрибута координаты `cell.get("r")` (например, `C2` -> индекс 2) и размещать значение строго по индексу, заполняя пропущенные ячейки пустыми строками `""`.
2. **F08 (Серверное сохранение партии импорта):**
   - В `backend/app/importer.py`:
     * В `preview_import_batch` сохранять валидированный план импорта (или вычислять детерминированный SHA-256 хеш проверенных строк).
     * В `commit_import_batch` валидировать обязательные поля каждой строки; не отбрасывать строки молча, а выбрасывать `APIError("VALIDATION_ERROR", ..., 422)`.
3. **F09 (Создание карточки после импорта ВУЗа):**
   - В `backend/app/importer.py`:
     * При создании организации выдавать импортировавшему пользователю полные права: `OrganizationAccess(organization_id=org.id, user_id=user.id, read_all=True, can_create=True)`.

### R4. Пакет 4: PATCH и конкурентность интеграций (F11, F12)
1. **F11 (Защита от null в PATCH):**
   - В `backend/app/schemas.py:InteractionUpdate`:
     * Использовать валидатор, запрещающий передачу явного `null` для обязательных полей (`title`, `cycle_label`).
   - В `backend/app/services.py:update_interaction`:
     * В хешировании идемпотентности разделять отсутствие ключа и явную передачу пустого значения через `body.model_dump(exclude_unset=True)`.
2. **F12 (Атомарность сверки и source_revision):**
   - В `backend/app/integrations/service.py`:
     * В `resolve_inbox_item`: выполнять условный CAS-захват статуса заявки: `update(IntegrationInbox).where(id == inbox_id, status == pending).values(status=processing)`. Если обновлено 0 строк — выбрасывать конфликт 409 (заявка уже обрабатывается).
     * В функции обработки `LearningMetric`: проверять `source_revision`: не перезаписывать метрику, если входящая ревизия старше текущей в базе данных.

### R5. Инварианты безопасности и целостности
1. Каталог `docs/architecture/` строго READ-ONLY (0 байт изменений).
2. Запрещено добавлять сторонние пакеты в `backend/requirements.txt` (Ponytail Ladder: стандартные библиотеки Python и существующие зависимости).
3. Все проверки оракула `docs/checks/verify_infra.py` и функциональных оракулов (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) обязаны оставаться в статусе PASS.
4. Все существующие тесты бэкенда (`backend/tests/`) обязаны проходить без регрессий (361+ passed).
5. Нулевой дрейф схемы БД: `alembic check` подтверждает полное совпадение с `Base.metadata`.
6. Сборка фронтенда и проверка типов (`npx tsc --noEmit && npx vite build`) проходят без ошибок.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] F02: Миграция воркфлоу фильтруется по области видимости пользователя (`scope_clause`) и проверяет `validate_subject` для обязательных статусов.
- [ ] F03: Учебные показатели фильтруются по `visible_organization_ids` для всех ролей.
- [ ] F04: Загрузка вложений требует права `interactions.write` (возвращает 403 при read-only).
- [ ] F05: Экспорт PDF формирует читаемый кириллический текст и не обрезает жестко ячейки до 22 символов.
- [ ] F06: Контракт `created_report` синхронизирован между бэкендом и фронтендом.
- [ ] F07: Парсер XLSX корректно учитывает разреженные ячейки по координате `r`.
- [ ] F08: Пакет импорта строго валидируется на этапе commit.
- [ ] F09: Импорт организации предоставляет создателю права `read_all=True, can_create=True`.
- [ ] F10: Подсчет активных этапов фильтрует нулевые группы, экспорт привязан к `report_run_id`.
- [ ] F11: Запрещен явный `null` в PATCH-запросах для `title` и `cycle_label`.
- [ ] F12: Сверка заявок защищена условным CAS (409 на конфликт), метрики проверяют `source_revision`.

### Верификация
- [ ] Проверка всех 4 системных оракулов: `python3 docs/checks/verify_infra.py && python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py` — PASS.
- [ ] Все тесты бэкенда: `./backend/.venv/bin/pytest backend/tests/` проходят без регрессий (361+ passed).
- [ ] Проверка TypeScript и сборка фронтенда: `cd frontend && npx tsc --noEmit && npx vite build --configLoader native` — PASS.
- [ ] Каталог `docs/architecture/` чист (`git status docs/architecture` чист, 0 байт изменений).
- [ ] Нулевой дрейф схемы Alembic: `alembic.command.check(cfg)` возвращает 0 расхождений.


## 2026-09-25T19:10:45Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Детальный аудит и реализация сквозного прохождения 10 полей из ТЗ (раздел 4, п. 1): «Название ВУЗа, Вендор, ПО, Номер договора, Подписание лицензии, Срок действия лицензии (год), Статус по передачи, ФИО Менеджера, Ответственные от ВУЗа, Комментарий» во всей цепочке (Импорт XLS/XLSX -> Модели БД -> REST API -> Форма создания -> Карточка взаимодействия -> Отчеты). Добавить выбор контакта и стартовый комментарий в модальное окно создания, селектор лицензии ПО в редактирование параметров, расширить синонимы и парсинг мастера импорта с созданием License и комментария, покрыть автотестами, подтвердить неизменность всех 4 системных оракулов ТЗ и сборку фронтенда.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Модальное окно «Новое взаимодействие» (`frontend/src/forms.tsx`)
1. Сохранить все существующие обязательные поля формы (`title`, `organization_id`, `program_id`, `product_id`, `cycle_label`, `owner_id`).
2. Добавить опциональное выпадающее поле «Контактное лицо от ВУЗа» (`contact_id`):
   - Динамически фильтровать контакты по выбранной образовательной организации (`catalogs.contacts.filter(c => c.organization_id === form.organization_id && c.active)`).
   - Сбрасывать выбранный контакт при смене организации.
3. Добавить опциональное многострочное поле «Комментарий к старту взаимодействия» (`comment`):
   - Передавать `comment` в теле запроса `POST /api/v1/interactions`.
4. В бэкенде (`backend/app/schemas.py` и `backend/app/services.py`):
   - В `InteractionCreate` добавить опциональное поле `comment: str | None = Field(default=None, max_length=5000)`.
   - В `create_interaction` при наличии непустого `comment` сразу создавать связанную запись `Comment` (с автором `user`, текущим `visit_id` и событием `comment_added`).

### R2. Модальное окно «Редактировать параметры» (`frontend/src/views/InteractionPage.tsx`)
1. В форму редактирования параметров `EditModal` добавить селектор «Лицензия ПО» (`license_id`):
   - Список лицензий фильтровать по организации взаимодействия: `(catalogs.licenses || []).filter(l => l.organization_id === item.organization_id && (!form.product_id || l.product_id === form.product_id))`.
   - Отображать наименование продукта, вендора, статус передачи и срок действия лицензии.
2. Включать выбранный `license_id` в отправляемый `InteractionUpdatePayload` (уже поддержано в `services.py:update_interaction` с валидацией принадлежности организации и продукта).
3. В информационном блоке карточки (`detail-facts`) отображать статус, срок действия и дату подписания лицензии, а также вендора ПО (`product_vendor`), если они привязаны.

### R3. Мастер импорта Excel (`backend/app/importer.py`)
1. Расширить словарь синонимов `COLUMN_SYNONYMS`:
   - `vendor`: `["вендор", "vendor", "производитель"]`
   - `license_signed_on`: `["подписание лицензии", "дата подписания лицензии", "лицензия подписана", "license_signed_on", "дата лицензии"]`
   - `license_term_years`: `["срок действия лицензии (год)", "срок действия лицензии", "срок действия", "срок лицензии", "срок действия (год)", "license_term_years", "term_years"]`
   - `license_transfer_status`: `["статус по передачи", "статус передачи", "статус передачи лицензии", "статус по передаче", "transfer_status", "license_transfer_status"]`
   - `comment`: `["комментарий", "комментарии", "комментарий к старту взаимодействия", "начальный комментарий", "заметка", "примечание", "comment", "notes"]`
2. В `preview_organizations_import` извлекать указанные поля и передавать их в словарь `data` каждой строки предварительного просмотра.
3. В `commit_organizations_import`:
   - При наличии продукта и/или полей лицензии находить или создавать запись `License`, привязанную к организации, продукту и договору.
   - При наличии комментария сохранять его в `notes` созданного контакта и, если для организации создано/найдено взаимодействие, создавать начальную запись `Comment`.
   - Возвращать в итоговом словаре `created_licenses` без нарушения обратной совместимости существующих ключей.

### R4. Сквозная верификация и автотесты
1. Добавить тесты в `backend/tests/test_audit_remediation_f02_f12.py`:
   - Создание взаимодействия с привязкой контакта и начальным комментарием через `POST /api/v1/interactions`.
   - Проверка наличия созданного `Comment` в истории взаимодействия.
   - Импорт файла Excel/CSV с полями лицензии и комментария с проверкой создания связанных записей `License` и `Comment`.
2. Подтвердить сохранение всех системных контрактов и неизменность оракулов:
   - `docs/checks/verify_infra.py` — PASS.
   - `docs/checks/verify_workflow.py` — PASS.
   - `docs/checks/verify_reports.py` — PASS.
   - `docs/checks/verify_plan.py` — PASS.
3. Проверить сборку фронтенда:
   - `npx tsc --noEmit` — 0 ошибок.
   - `npx vite build --configLoader native` — успешная сборка.
4. Проверить полный регрессионный сьют бэкенда (`pytest backend/tests/`).
5. Неприкосновенность архитектуры: `docs/architecture/` — 0 байт изменений.
6. Соблюдение принципа Ponytail Ladder: 0 сторонних зависимостей.

---

## Acceptance Criteria

### Функциональная корректность
- [ ] В модальном окне «Новое взаимодействие» доступен выбор контакта от выбранного ВУЗа и текстовое поле для стартового комментария.
- [ ] При создании взаимодействия с комментарием на бэкенде автоматически создается запись `Comment`.
- [ ] В окне «Редактировать параметры» доступен селектор `license_id`, данные сохраняются через `PATCH /interactions/{id}`.
- [ ] В `COLUMN_SYNONYMS` импортера добавлены синонимы для вендора, полей лицензии и комментария.
- [ ] При коммите импорта создаются связанные записи `License` и комментарий при их наличии в файле.
- [ ] Карточка взаимодействия отображает параметры лицензии и вендора.

### Верификация и качество
- [ ] Все 4 системных оракула ТЗ (`verify_infra`, `verify_workflow`, `verify_reports`, `verify_plan`) возвращают PASS.
- [ ] Добавлены тесты в `test_audit_remediation_f02_f12.py`, все тесты бэкенда проходят (374+ passed, 0 failed).
- [ ] Проверка TypeScript и сборка фронтенда проходят чисто (`npx tsc --noEmit && npx vite build`).
- [ ] Нулевой дрейф схемы Alembic.
- [ ] `docs/architecture/` строго нетронут (0 байт изменений).

## 2026-09-25T21:11:36Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Устранить две подтверждённые ошибки UI/UX в frontend: ролевой доступ к кнопке импорта каталогов (только для supervisor, administrator, admin) и исправление взаимодействия с комментариями/передачей ответственного (очистка полей ввода после успешной отправки, объединение событий и комментариев в единый хронологический таймлайн без дублирования).

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Ролевой доступ к кнопке импорта каталогов (`frontend/src/views/CatalogPage.tsx`)
- Скрыть кнопку «Импорт каталогов» для роли `manager`, которой запрещено создание организаций (бэкенд возвращает 403 Forbidden).
- Отображать кнопку «Импорт каталогов» исключительно для пользователей с привилегированными ролями (`isPrivileged`: `supervisor`, `administrator`, `admin`).
- Сохранить корректное отображение кнопки «Миграция процессов» (уже ограниченной `isPrivileged`).

### R2. Очистка полей ввода после успешной мутации (`frontend/src/views/InteractionPage.tsx`)
- После успешной отправки комментария (`POST /api/v1/interactions/:id/comments`) очищать поле ввода текста комментария (`setComment('')`).
- После успешной передачи взаимодействия новому менеджеру (`POST /api/v1/interactions/:id/assignments`) очищать поля ввода причины (`setReason('')`) и сбрасывать выбранного ответственного (`setOwner('')`).

### R3. Единый хронологический таймлайн без дублирования (`frontend/src/views/InteractionPage.tsx`)
- В блоке «История решений» (`panel timeline-panel`):
  - Исключить двойной рендеринг комментариев: поскольку добавление комментария порождает событие `InteractionEvent(type='comment_added')`, комментарии не должны выводиться повторно отдельным блоком после всех событий.
  - Объединить события и любые автономные комментарии в единый хронологический список, отсортированный по времени (`effective_at` / `created_at`).
  - Для событий типа `comment_added` / `comment` сохранять стилизацию точки таймлайна оранжевым цветом (`timeline-dot tone-orange`).
  - Отображать актуальное суммарное количество записей в бейдже заголовка.

## Acceptance Criteria

### UI/UX & Roles
- [ ] Пользователь с ролью `manager` не видит кнопку «Импорт каталогов» на странице справочников.
- [ ] Пользователи с ролями `supervisor`, `administrator`, `admin` видят кнопку «Импорт каталогов».
- [ ] При добавлении комментария текстовое поле очищается сразу после успешного ответа сервера.
- [ ] При передаче карточки текстовое поле причины очищается сразу после успешного ответа сервера.
- [ ] В истории решений комментарии отображаются строго один раз в хронологическом порядке относительно переходов и смены ответственного.

### System Verification & Code Quality
- [ ] Сборка фронтенда проходит без ошибок: `cd frontend && npx tsc --noEmit && npx vite build --configLoader native`.
- [ ] Все тесты бэкенда проходят без регрессий: `./backend/.venv/bin/pytest backend/tests/ -q`.
- [ ] Все 4 системных оракула ТЗ возвращают PASS: `python3 docs/checks/verify_infra.py && python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py`.
- [ ] Нулевой дрейф схемы Alembic (`test_migrations.py`).
- [ ] Архитектурная директория `docs/architecture/` остаётся строго неизменной (0 байт изменений).
- [ ] Файл `.env` отсутствует в корне репозитория.

## 2026-09-25T23:05:44Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Аудит и устранение двух проблем в проекте: исправление Keycloak Logout («Invalid redirect uri») при входе через 127.0.0.1 / несовпадении завершающего слэша с гарантированным сбросом стейта сессии, и исправление классификации кнопок переходов воркфлоу в карточке взаимодействия (устранение хардкодов по состояниям, строгое разграничение по `kind`: forward, skip_optional, rework, cycle, cancellation, отображение номера шага «Этап X из 13: Название» в шапке этапа, проброс `kind` в `allowed_transitions` и добавление модульных тестов для всех 29 переходов).

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Исправление Keycloak Logout («Invalid redirect uri») (`deploy/keycloak/rtk-crm-realm.json`, `frontend/src/auth.tsx`)
1. В `deploy/keycloak/rtk-crm-realm.json` для клиента `rtk-crm-web`:
   - В `redirectUris` добавить: `"http://127.0.0.1:3000/*"`, `"http://127.0.0.1:5173/*"`.
   - В `webOrigins` добавить: `"http://127.0.0.1:3000"`, `"http://127.0.0.1:5173"`, `"+"`.
   - В `attributes["post.logout.redirect.uris"]` установить: `"+##http://localhost:3000/*##http://localhost:3000##http://127.0.0.1:3000/*##http://127.0.0.1:3000##http://localhost:5173/*##http://localhost:5173##http://127.0.0.1:5173/*##http://127.0.0.1:5173"`.
2. В `frontend/src/auth.tsx`:
   - В функции `logout` передавать безопасный fallback для `redirectUri` (`window.location.origin + /` или `window.location.origin`).
   - Гарантированно сбрасывать локальное состояние сессии: `setMe(null)`, `setAuthenticated(false)` (в т.ч. при ошибке вызова `keycloak.logout`).

### R2. Исправление кнопок переходов воркфлоу и номера шага (`frontend/src/views/InteractionPage.tsx`, `backend/app/workflow.py`)
1. В `backend/app/workflow.py`:
   - В `allowed_transitions` включить поле `"kind": edge.get("kind", "forward")`, чтобы фронтенд всегда получал канонический тип перехода.
2. В `frontend/src/views/InteractionPage.tsx`:
   - Устранить хардкоды по кодам состояний (`t.to === 'document_revision'`, `t.to === 'classes'`).
   - Классифицировать действия строго по `kind` (с fallback на `workflow.transitions` по `t.code`):
     - `t.kind === 'forward'` -> `Перейти: ${t.name}` (variant="primary", Icon name="arrow")
     - `t.kind === 'skip_optional'` -> `Пропустить: ${t.name}` (variant="secondary", Icon name="arrow")
     - `t.kind === 'rework'` -> `Вернуть: ${t.name}` (variant="secondary", Icon name="refresh")
     - `t.kind === 'cycle'` -> `Повторный цикл: ${t.name}` (variant="secondary", Icon name="refresh")
     - `t.kind === 'cancellation'` (или `to === 'cancelled'`) -> `Отменить взаимодействие` (variant="danger", Icon name="close")
   - В карточке в шапке блока текущего этапа отображать номер шага:
     - Для рабочих этапов: `Этап ${step} из 13: ${item.state_name}` (где `step` берется из `workflow.states` по `source_step` или порядковому номеру).
     - Для терминальных этапов: сохранить исходное отображение или `Завершено: ${item.state_name}`.

### R3. Модульные тесты и верификация (`backend/tests/`)
1. Создать/расширить модульные тесты в `backend/tests/` (например, `backend/tests/test_workflow_button_classification.py`):
   - Проверить наличие поля `kind` во всех переходах `allowed_transitions` для всех рабочих состояний.
   - Проверить правильность классификации (подпись кнопки, вариант стиля, иконка) для всех 29 переходов базового воркфлоу.
   - Проверить контракт Keycloak realm json на наличие допустимых URI редиректа для 127.0.0.1 и localhost.
2. Проверить сборку фронтенда: `cd frontend && npx tsc --noEmit && npx vite build --configLoader native`.
3. Запустить полный тестовый сьют: `./backend/.venv/bin/pytest backend/tests/ -q`.
4. Подтвердить сохранение всех 4 системных оракулов ТЗ: `verify_infra.py`, `verify_workflow.py`, `verify_reports.py`, `verify_plan.py`.
5. Сохранить неизменность `docs/architecture/` (0 байт изменений) и отсутствие `.env` в корне.

## Acceptance Criteria

### Keycloak & Authentication
- [ ] `deploy/keycloak/rtk-crm-realm.json` содержит URI `http://127.0.0.1:3000/*` и `http://127.0.0.1:5173/*` в `redirectUris`.
- [ ] `webOrigins` содержит `http://127.0.0.1:3000`, `http://127.0.0.1:5173` и `+`.
- [ ] `post.logout.redirect.uris` содержит разрешенные шаблоны выхода для localhost и 127.0.0.1.
- [ ] `logout` в `frontend/src/auth.tsx` гарантированно сбрасывает `me` и `authenticated`.

### Workflow UI & Step Numbering
- [ ] Прямой шаг 10 -> 11 («Актуализация учебной программы» -> «Ведение занятий») отображается как `Перейти: Ведение занятий` (вариант primary).
- [ ] Шаг 4 -> 5 («Обмен документами» -> «Корректировка документов») отображается как `Перейти: Корректировка документов` (вариант primary).
- [ ] Возврат на доработку отображается как `Вернуть: ...` (вариант secondary).
- [ ] Повторный цикл отображается как `Повторный цикл: ...` (вариант secondary).
- [ ] Пропуск опционального этапа отображается как `Пропустить: ...` (вариант secondary).
- [ ] Отмена отображается как `Отменить взаимодействие` (вариант danger).
- [ ] В шапке текущего этапа отображается номер шага: «Этап 10 из 13: Актуализация учебной программы».

### System Invariants
- [ ] Сборка фронтенда чистая: `tsc --noEmit` (0 ошибок) и `vite build`.
- [ ] Все 4 оракула ТЗ возвращают 100% PASS.
- [ ] Все тесты бэкенда проходят без ошибок (`pytest backend/tests/`).
- [ ] Нулевой дрейф схемы Alembic.
- [ ] `docs/architecture/` строго 0 байт изменений.
- [ ] Файл `.env` отсутствует в корне репозитория.


## 2026-09-26T08:44:56Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Реализация адаптивного дашборда администратора («Панель системного управления CRM» с телеметрией, кнопками быстрого перехода и пояснением 152-ФЗ при сохранении строгой изоляции коммерческих воронок) и универсального импорта организаторских файлов (автоопределение и импорт «Вендоры.xlsx» с поддержкой мульти-продуктов, «Загрузка пользователей.xlsx», а также приём и обработка файла выгрузки оплат LMS «Данные оплат.json» с защитой от null-элементов, обновлением очереди IntegrationInbox и метрик LearningMetrics).

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Адаптивный дашборд Администратора («Обзор») с соблюдением 152-ФЗ (`backend/app/services.py`, `frontend/src/views/WorkspaceViews.tsx`)
1. **Сохранение изоляции 152-ФЗ на бэкенде**:
   - Не ослаблять `scope_clause(user)`: у администратора без явных грантов `OrganizationAccess` число доступных коммерческих взаимодействий остаётся строго равным `0`.
   - В функции `dashboard(db, user)` при `user.role in ("administrator", "admin")` возвращать блок `system_stats`:
     * `total_users`: общее количество пользователей системы (`User`);
     * `total_organizations_catalog`: общее число организаций в каталоге (`Organization`);
     * `total_programs_catalog`: общее число ИТ-программ (`Program`);
     * `total_products_catalog`: общее число ИТ-продуктов (`Product`);
     * `total_inbox_pending`: число входящих заявок в очереди интеграций со статусом `pending` (`IntegrationInbox`);
     * `lms_health_status`: статус доступности адаптеров интеграций.
2. **Фронтенд «Панель системного управления CRM» (`WorkspaceViews.tsx`)**:
   - Для пользователей с ролью `administrator` / `admin` отображать специализированный интерфейс дашборда:
     * Системные карточки-метрики: «Всего пользователей», «Организаций в каталоге», «ИТ-продуктов и вендоров», «Заявок на сверку в очереди интеграций».
     * Информационный блок безопасности 152-ФЗ / ФСТЭК №117:
       *«Режим системного администратора: в соответствии с регламентом 152-ФЗ прямой доступ к коммерческим воронкам менеджеров изолирован. Используйте вкладки «Интеграции», «Справочники» и «Отчёты» для конфигурирования системы.»*
     * Кнопки быстрых действий для перехода: «Импорт каталогов» (`catalogs`), «Шлюз интеграций» (`integrations`), «Миграция процессов v1/v2» (`catalogs`), «База знаний и регламенты» (`help`).
     * Если у администратора есть назначенные гранты организаций (`total_interactions > 0`) — отображать и воронку доступных процессов.

### R2. Универсальный импорт файлов каталогов: Вендоры и Пользователи (`backend/app/importer.py`, `frontend/src/views/CatalogPage.tsx`)
1. **Каталог вендоров и отечественного ПО (`Вендоры.xlsx`)**:
   - Автоматически распознавать колонки: `Контакт` / `ФИО представителя`, `Телефон`, `Email`, `Вендор` / `Компания`, `ПО` / `Продукты` / `Программное обеспечение`.
   - Автоматическое переключение в режим вендоров/продуктов при наличии колонок вендора/ПО и отсутствии «Название вуза».
   - Поддержка разбора ячеек с несколькими продуктами через запятую или точку с запятой (например: `«RT.DataLake», «RT.Warehouse»`).
   - Автоматическое создание/поиск вендора (`Organization` с типом `vendor` и контактом представителя) и связывание продуктов (`Product` с заполнением `name` и `vendor`). Не требовать предварительного наличия продуктов в БД.
2. **Каталог ответственных / пользователей (`Загрузка пользователей.xlsx`)**:
   - Распознавать колонки: `ФИО`, `Email`, `Телефон`, `Роль` (менеджер / руководитель / администратор), `Команда` / `Отдел`.
   - Создавать или обновлять пользователей (`User`) в CRM с валидацией дубликатов по email/логину.
3. **Обратная совместимость**:
   - Полное сохранение импорта вузов, контактов, договоров и лицензий (10-колоночный формат ТЗ).
4. **Интерфейс мастера импорта (`CatalogPage.tsx`)**:
   - Поддержка автоопределения или ручного выбора типа файла (Вузы и лицензии / Вендоры и ПО / Пользователи) с корректным предпросмотром таблицы колонок.

### R3. Загрузка JSON-файла оплат и заявок LMS (`backend/app/main.py`, `backend/app/integrations/service.py`, `frontend/src/views/IntegrationsView.tsx`)
1. **Эндпоинт `POST /api/v1/integrations/upload/json`**:
   - Приём сырого JSON или multipart-формы с файлом `.json`.
   - Проверка прав: доступен ролям `supervisor` и `administrator`.
   - **Защита от сбоя**: устойчивая обработка массивов с `null` элементами (пропуск `null` с подсчётом `skipped_nulls`).
   - Парсинг полей: `"Номер заявки"` (`external_id`), `"Курс"` (сопоставление с `Program`), `"Фамилия"`, `"Имя"`, `"Отчество"`, `"Телефон"`, `"Email"`, `"Номер потока"`.
   - Создание записей `IntegrationInbox` со статусом `pending` и типом `lms_order`.
   - Обновление агрегированных метрик в `LearningMetric` (заявки, оплаты, конверсия).
   - Ответ: `{"total_records": N, "processed": M, "skipped_nulls": K, "message": "Файл оплат LMS успешно обработан"}`.
2. **Интерфейс Шлюза интеграций (`IntegrationsView.tsx`)**:
   - Добавление кнопки «Загрузить выгрузку оплат LMS (.json)» и модального окна загрузки файла.
   - Автоматический вызов `loadAll()` / `reload()` после успешной загрузки для обновления метрик и таблицы очереди.

### R4. Автотесты и верификация
1. Разработать модульные тесты:
   - `backend/tests/test_vendors_import.py`: импорт структуры `Вендоры.xlsx`, создание записей продуктов с вендором, парсинг мульти-продуктов через запятую, импорт пользователей `Загрузка пользователей.xlsx`.
   - `backend/tests/test_lms_json_upload.py`: загрузка JSON-файла с `null` элементом, создание заявок `IntegrationInbox`, расчёт метрик `LearningMetric`, проверка прав доступа.
2. Подтвердить сохранение всех системных контрактов:
   - Тест `test_administrator_has_zero_implicit_access_to_commercial_interactions` в `test_adversarial_security_invariants.py` — строго 100% PASS.
   - Все 4 системных оракула ТЗ (`verify_infra.py`, `verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) — 100% PASS.
   - Все существующие тесты бэкенда (401+) — PASS без регрессий.
   - Сборка фронтенда: `cd frontend && npx tsc --noEmit && npx vite build --configLoader native` — 0 ошибок.
   - Дрейф схемы Alembic — 0.
   - Каталог `docs/architecture/` — строго 0 байт изменений.
   - Отсутствие `.env` в корне репозитория.

## Acceptance Criteria

### Administrator Dashboard
- [ ] Администратор видит информативный дашборд со статистикой пользователей, каталогов, очереди интеграций и кнопками быстрого перехода.
- [ ] Для администратора отображается пояснение о регламенте 152-ФЗ / ФСТЭК №117 об изоляции коммерческих воронок менеджеров.
- [ ] При отсутствии назначенных грантов организаций коммерческие взаимодействия администратора строго изолированы (`total_interactions == 0`).
- [ ] Тест `test_administrator_has_zero_implicit_access_to_commercial_interactions` проходит успешно.

### Universal Importer
- [ ] Файл формата `Вендоры.xlsx` успешно импортируется без ошибок отсутствия колонки «Название вуза».
- [ ] Продукты, перечисленные через запятую/точку с запятой, создаются как отдельные записи `Product` с корректно привязанным вендором.
- [ ] Файл формата `Загрузка пользователей.xlsx` создает/обновляет учетные записи `User` с сохранением ролей и валидацией email.
- [ ] Базовый импорт вузов и лицензий (10 полей ТЗ) продолжает работать без регрессий.

### LMS Payments Upload
- [ ] Эндпоинт `POST /api/v1/integrations/upload/json` успешно принимает JSON-файл оплат и заявок.
- [ ] Наличие элемента `null` в массиве не приводит к ошибке 500 (пропускается с фиксацией в `skipped_nulls`).
- [ ] Заявки создаются в `IntegrationInbox` в статусе `pending`, а метрики `LearningMetric` обновляются.
- [ ] В UI `IntegrationsView.tsx` доступна кнопка и модальное окно загрузки выгрузки оплат с последующим обновлением данных.

### Quality & Invariants
- [ ] `cd frontend && npx tsc --noEmit && npx vite build --configLoader native` завершается с 0 ошибок.
- [ ] `pytest backend/tests/` проходит на 100% (401+ тестов).
- [ ] Все 4 системных оракула возвращают PASS.
- [ ] `docs/architecture/` не содержит изменений (0 diff).
- [ ] Файл `.env` отсутствует в репозитории.


## 2026-09-26T11:12:56Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Full team (распределённая команда параллельной реализации)

Использовать полную команду агентов (Full team) для распределённой реализации, независимого состязательного ревью и итогового аудита приёмки.
Задача: устранение первопричины в автоопределении типа файла организаторов «Загрузка пользователей.xlsx», добавление разбора и склейки составных колонок ФИО («Фамилия» + «Имя» + «Отчество»), очистки телефонов, назначения роли по умолчанию («manager»), а также интерактивного переключения формата данных в мастере импорта на этапе предпросмотра без сброса файла.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Исправление автоопределения типа файла и параметров вызова (`backend/app/importer.py`)
1. **Передача `filename`**:
   - В функции `_detect_file_type(headers: list[str], filename: str | None = None) -> str` добавить параметр `filename: str | None = None`.
   - Передавать `filename` в `_detect_file_type` из `parse_tabular_file`, `preview_organizations_import` и `commit_organizations_import`.
2. **Сигнатуры в `filename`**:
   - Если в `filename` присутствуют маркеры пользователей (`пользовател`, `user`, `сотрудник`, `слушател`, `студент`, `кадр`, `персонал`) — классифицировать файл как `"users"`.
3. **Анализ заголовков таблицы `headers`**:
   - Если в заголовках присутствуют атрибуты физлиц / слушателей / сотрудников (`снилс`, `паспорт`, `рождение`, `регистрация`, `диплом`, `профессия`, `отчество`) ИЛИ присутствует пара (`фамилия` и хотя бы одно из: `имя`, `email`, `телефон`) при отсутствии явной колонки вуза (`название вуза`, `наименование вуза`) — классифицировать файл как `"users"`.
   - Если присутствуют маркеры вендоров/продуктов (`вендор`, `по`, `продукт`, `программное обеспечение`) — `"vendors"`.
   - Только при наличии колонок вуза/договора либо при отсутствии других признаков — `"organizations"`.

### R2. Склейка составных колонок ФИО и нормализация пользователей (`backend/app/importer.py`)
1. **Распознавание колонок в `_match_header(header_text, file_type=None)`**:
   - Распознавать раздельные колонки:
     * `last_name`: `фамилия`, `last_name`, `surname` (с исключением дательного падежа и диплома: `диплом`, `падеж`);
     * `first_name`: `имя`, `first_name` (с исключением дательного падежа);
     * `patronymic`: `отчество`, `patronymic`, `отчествопри наличии`, `отчество (при наличии)`.
2. **Сборка полного ФИО в `parse_tabular_file` (`file_type == "users"`)**:
   - Склеивать полное имя:
     ```python
     full_name = " ".join(filter(None, [row_dict.get("last_name"), row_dict.get("first_name"), row_dict.get("patronymic")])).strip()
     if full_name:
         row_dict["name"] = full_name
     ```
   - На файле `Загрузка пользователей.xlsx` имена должны получаться строго полными:
     * «Черепанова Светлана Васильевна»
     * «Кричанов Максим Сергеевич»
     * «Григорьев Станислав Семенович»
     * «Осипенко Ирина Викторовна»
     * «Иванов Михаил Петрович»
3. **Дефолтная роль и телефоны**:
   - При отсутствии колонки роли назначать по умолчанию роль `"manager"`.
   - Сохранять телефон в очищенном виде (только цифры, например `79990234365`).

### R3. Интерактивная смена формата и плашка подсказки в UI (`frontend/src/views/CatalogPage.tsx`)
1. **Шаг 1 (`ImportWizardModal`)**:
   - При выборе файла (`validateAndSetFile`), если выбран режим «Автоопределение», проверять имя файла: если в имени есть маркеры пользователей (`пользовател`/`user`), отображать информационную плашку-подсказку с распознанным типом.
2. **Шаг 2 («Предпросмотр»)**:
   - Заменить статическую надпись `Формат: ...` на интерактивный селектор (`<select>`):
     * «Образовательные организации (вузы, договоры)» (`organizations`)
     * «Вендоры и отечественное ПО» (`vendors`)
     * «Пользователи и ответственные сотрудники» (`users`)
   - При изменении значения селектора повторно отправлять запрос `/imports/organizations/preview?import_type=${newType}` с тем же файлом через `rePreviewWithFormat(newType)`, позволяя пользователю переключить формат в один клик без возврата на Шаг 1.

### R4. Тестирование и верификация (Definition of Done)
1. **Автотест в `backend/tests/test_vendors_import.py`**:
   - Тест `test_organizer_users_xlsx_file_auto_detection_and_parsing`:
     * Загружает реальный файл `данные предоставленные организаторами/Загрузка пользователей.xlsx`;
     * Вызывает `preview_organizations_import(db, user, file_bytes, "Загрузка пользователей.xlsx")` без передачи query-параметра `import_type`;
     * Проверяет: `detected_type == "users"`, `total_rows == 5`, `valid_rows == 5`, `error_count == 0`;
     * Проверяет склеивание ФИО: `"Черепанова Светлана Васильевна"`, `"Кричанов Максим Сергеевич"`, `"Григорьев Станислав Семенович"`, `"Осипенко Ирина Викторовна"`, `"Иванов Михаил Петрович"`;
     * Выполняет `commit_organizations_import` и проверяет создание в БД ровно 5 пользователей с корректными email, телефонами и ФИО.
2. **Полный регресс и инварианты**:
   - Все тесты бэкенда (`pytest backend/tests`) проходят со 100% успехом (>= 421 passed, 0 failed).
   - Все 4 системных оракула (`verify_infra.py`, `verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) — PASS.
   - Сборка фронтенда (`npx tsc --noEmit && npx vite build`) — 0 ошибок.
   - `docs/architecture/` — строго 0 байт diff (READ-ONLY).
   - Корневой `.env` отсутствует.

## Acceptance Criteria

### Auto-Detection & Parsing
- [ ] Функция `_detect_file_type` принимает `filename` и определяет `Загрузка пользователей.xlsx` как `"users"` без `import_type`.
- [ ] Распознаются колонки `last_name`, `first_name`, `patronymic` с защитой от ложных совпадений.
- [ ] В `parse_tabular_file` для `users` составные части склеиваются в полное имя `name`.
- [ ] Все 5 строк из файла организаторов имеют `is_valid: True` и `errors: []`.
- [ ] `commit_organizations_import` создаёт 5 пользователей со статусом `active: True`, ролью `"manager"`, email и телефонами.

### UI / UX
- [ ] В `ImportWizardModal` на Шаге 1 выводится плашка подсказки при распознавании имени файла.
- [ ] На Шаге 2 доступен `<select>` смены формата (`organizations`, `vendors`, `users`), повторно запрашивающий `preview` с тем же файлом без перехода назад.

### Verification & Invariants
- [ ] Тест `test_organizer_users_xlsx_file_auto_detection_and_parsing` проходит.
- [ ] Полный тестовый сьют `pytest backend/tests/` проходит без ошибок.
- [ ] Все 4 оракула — PASS.
- [ ] `npx tsc --noEmit` и `npx vite build` — 0 ошибок.
- [ ] `docs/architecture/` — 0 изменений.


## 2026-09-26T12:58:45Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Full team (распределённая параллельная команда)

Использовать полную команду агентов (Full team) для распределённой параллельной реализации, независимого состязательного ревью и итогового аудита приёмки.
Задача: Доменное разделение сотрудников CRM и обучающихся LMS (Устранение концептуальной ошибки): перенос слушателей курсов LMS из операторской таблицы пользователей `User` в контур интеграций `IntegrationInbox` (entity_type="learner"), очистка справочника ответственных сотрудников РТК, загрузка анкет и паспортов студентов в шлюз интеграций с взаимным обогащением по оплатам из JSON и поддержкой сверки с воронкой вуза на этапе 11 («Ведение занятий»).

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Доменная чистота и защита справочника сотрудников (`User`, `services.py`)
1. **Зачистка таблицы `User`**:
   - Удалить ошибочно созданные записи обучающихся (`cherepanona-s`, `max_crich`, `grigorev355`, `osipenko833484`, `mp_ivanov`).
   - В таблице `User` должны находиться исключительно штатные сотрудники РТК (`manager-a`, `manager-b`, `supervisor`, `administrator` и др. реальные операторы).
2. **Изоляция в `catalogs.owners` (`backend/app/services.py`)**:
   - В справочнике `owners` возвращать строго сотрудников CRM с ролями `manager`, `supervisor`, `administrator`.
   - Исключить попадание любых внешних физлиц / слушателей LMS в список ответственных менеджеров.

### R2. Подсистема анкет слушателей LMS (`backend/app/integrations/`, `backend/app/importer.py`, `backend/app/main.py`)
1. **Парсинг анкет обучающихся (`Загрузка пользователей.xlsx`)**:
   - В `backend/app/integrations/service.py` реализовать обработку анкет обучающихся `process_lms_learners_file(db, user, file_bytes, filename)`.
   - Извлекать все поля анкеты: Фамилия, Имя, Отчество, Телефон, Email, СНИЛС, Серия и Номер паспорта, Кем выдан, Дата выдачи, Код подразделения, Дата рождения, Адрес регистрации, Образование, Профессия, Вуз по диплому, Номер диплома.
   - Сохранять записи в `IntegrationInbox`:
     * `source = "lms"`
     * `entity_type = "learner"`
     * `external_id = email` (или нормализованный телефон)
     * `payload = { ...все поля анкеты... }`
     * `status = "pending"`
2. **Взаимное обогащение с оплатами LMS (`Данные оплат.json`)**:
   - При наличии в `IntegrationInbox` заявки из `Данные оплат.json` с совпадающим email или телефоном связывать анкету слушателя с заказом на курс.
3. **Эндпоинты API**:
   - Добавить эндпоинт загрузки анкет слушателей `POST /api/v1/integrations/upload/learners` (multipart `.xlsx` / `.csv`).
   - При ошибочной загрузке файла слушателей в модалку каталогов (`/imports/organizations/preview`): автоопределение классифицирует файл как `"lms_learners"` и возвращает понятный ответ с перенаправлением в раздел «Интеграции», сохраняя данные в `IntegrationInbox` без засорения таблицы `User`.

### R3. Пользовательский интерфейс контура Интеграций и Справочников (`frontend/src/`)
1. **Вкладка «Справочники» (`CatalogPage.tsx`)**:
   - В карточке «Ответственные» отображать только штатных сотрудников РТК с указанием роли.
   - В модальном окне импорта каталогов при загрузке `Загрузка пользователей.xlsx` выводить информационное уведомление: *«Распознан реестр слушателей LMS. Данные перенаправлены в подсистему Интеграций»* со ссылкой/кнопкой перехода в «Интеграции».
2. **Вкладка «Интеграции» (`IntegrationsView.tsx`)**:
   - Две кнопки загрузки: «Загрузить заявки LMS (.json)» и «Загрузить анкеты слушателей (.xlsx)».
   - Таблица входящих заявок и слушателей с возможностью раскрытия полного профиля (паспорт, СНИЛС, контакты, диплом).
   - Рейтинг/ранжирование образовательных программ по востребованности (заявки, оплаты, конверсия, зачисленные студенты) на основе данных LMS.
   - Сверка (Reconciliation): возможность связать слушателя с вузом-партнером и учесть студента на этапе 11 («Ведение занятий»).

### R4. Тестирование и верификация (Definition of Done)
1. **Интеграционные тесты**:
   - Тест импорта анкет слушателей `Загрузка пользователей.xlsx` в `IntegrationInbox` (проверка всех полей ПДн в payload).
   - Тест связки анкеты слушателя с заявкой из `Данные оплат.json`.
   - Тест гарантии чистоты таблицы `User` и каталога `owners` (0 студентов в операторах CRM).
2. **Инварианты**:
   - Все 420+ тестов `pytest backend/tests/` проходят со 100% успехом.
   - 4 системных оракула (`verify_infra`, `verify_workflow`, `verify_reports`, `verify_plan`) — PASS.
   - Сборка фронтенда (`npx tsc --noEmit && npx vite build`) — 0 ошибок.
   - `docs/architecture/` — строго 0 байт изменений (READ-ONLY).
   - Корневой `.env` отсутствует.

## Acceptance Criteria

### Domain Purity
- [ ] В таблице `users` и эндпоинте `/catalogs` в поле `owners` содержатся только штатные операторы CRM.
- [ ] Обучающиеся физлица из файла организаторов отсутствуют в таблице `User`.

### LMS Integrations Subsystem
- [ ] Файл `Загрузка пользователей.xlsx` импортируется в `IntegrationInbox` с `entity_type="learner"`.
- [ ] Поля СНИЛС, паспортные данные, адрес и диплом сохранены в payload `IntegrationInbox`.
- [ ] Заявки из `Данные оплат.json` и анкеты из `Загрузка пользователей.xlsx` взаимно обогащаются по email/телефону.
- [ ] Доступен эндпоинт `POST /api/v1/integrations/upload/learners`.

### UI / UX
- [ ] В `CatalogPage` список ответственных содержит только сотрудников РТК.
- [ ] В `IntegrationsView` поддержана загрузка как JSON оплат, так и XLSX анкет слушателей.
- [ ] В интерфейсе интеграций отображаются детальные профили слушателей и аналитика востребованности программ.

### Verification & Invariants
- [ ] Интеграционные тесты проходят без ошибок.
- [ ] Полный сьют бэкенда (`pytest`) завершается с 0 failed.
- [ ] Все 4 оракула — PASS.
- [ ] `npx tsc --noEmit` и `npx vite build` — 0 ошибок.
- [ ] `docs/architecture/` — 0 изменений.

## 2026-09-26T15:58:00Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Безопасный предпросмотр (Preview) и контролируемое удаление (Delete) вложений в карточке взаимодействия: потоковый просмотр PDF и изображений (PNG/JPEG) внутри модального окна без сохранения на локальный диск, удаление файла с диска и БД с фиксацией события `attachment_deleted` в неизменяемом журнале аудита `interaction_events`, защитой CAS (`expected_revision`), изоляцией 152-ФЗ и проверкой прав доступа.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Бэкенд: потоковый предпросмотр и контролируемое удаление вложений (`backend/app/files.py`, `backend/app/main.py`)
1. **Потоковый предпросмотр (Inline disposition)**:
   - В эндпоинте `GET /api/v1/interactions/{interaction_id}/attachments/{attachment_id}/download` поддержать параметр `disposition: str = Query("attachment", regex="^(attachment|inline)$")`.
   - При `disposition == "inline"` возвращать `FileResponse` с `content_disposition_type="inline"`, позволяя браузеру отображать файл без принудительного сохранения на диск.
2. **Функция контролируемого удаления (`files.py:delete_attachment`)**:
   - Проверка области видимости через `item = scoped_interaction(db, user, interaction_id)`. Попытка доступа к чужой карточке возвращает HTTP 404.
   - Проверка прав: `require_permission(user, "interactions.write")`.
   - Проверка авторства: удалять вложение может автор файла (`attachment.uploaded_by == user.id`) либо пользователи с ролью `supervisor` или `administrator`. Иначе — HTTP 403 `FORBIDDEN`.
   - Проверка CAS: если передан `expected_revision`, валидировать через `cas(db, item, expected_revision)`. При несовпадении — HTTP 409 Conflict. Если ревизия не передана, выполнять инкремент `item.revision += 1`.
   - Физическое удаление файла с диска: `Path(attachment.file_path).unlink(missing_ok=True)`.
   - Фиксация в неизменяемом журнале аудита `interaction_events`:
     ```python
     append_event(
         db, item, user, "attachment_deleted", utcnow(),
         attachment_id=attachment.id, file_name=attachment.file_name,
         file_size=attachment.file_size, checksum=attachment.checksum,
     )
     ```
   - Удаление записи из БД: `db.delete(attachment)`.
   - Возврат: `{"status": "ok", "deleted_attachment_id": attachment_id, "revision": item.revision}`.
3. **Эндпоинт `DELETE` (`main.py`)**:
   - `DELETE /api/v1/interactions/{interaction_id}/attachments/{attachment_id}`.
   - Поддержка заголовка `Idempotency-Key` (до 200 символов) через `begin_command` / `finish_command`.
   - Query-параметр `expected_revision: int | None = None`.
   - Транзакционный коммит `db.commit()`.

### R2. Фронтенд: интерфейс предпросмотра и модальное окно удаления (`frontend/src/api.ts`, `frontend/src/views/InteractionPage.tsx`)
1. **Методы API (`api.ts`)**:
   - `previewAttachmentBlob(path: string): Promise<{ blobUrl: string; cleanup: () => void }>`: выполняет авторизованный `raw(path)`, создаёт `URL.createObjectURL(blob)`, возвращает функцию `cleanup` с `URL.revokeObjectURL(blobUrl)`.
   - `deleteAttachment(interactionId: string, attachmentId: string, expectedRevision?: number, key?: string): Promise<{ status: string; revision: number }>`.
2. **Кнопки действий в списке вложений (`InteractionPage.tsx`)**:
   - Для файлов `pdf`, `png`, `jpg`, `jpeg` добавить кнопку «Просмотр» (`variant="secondary"`).
   - Кнопка «Скачать» сохраняется без изменений.
   - Кнопка «Удалить» (`variant="ghost"`, цвет опасности): доступна автору загрузки, супервизору или администратору.
3. **Модальное окно предпросмотра (`AttachmentPreviewModal`)**:
   - PDF: нативный адаптивный `<iframe src={blobUrl} />` (высота 70vh, без рамок).
   - Изображения (PNG/JPEG): центрированный `<img src={blobUrl} />` с сохранением пропорций (`max-height: 70vh`).
   - Бинарные архивы и таблицы (ZIP, RAR, DOCX, XLSX): информационная плашка с иконкой формата, метаданными и кнопкой «Скачать для открытия в программе».
   - Кнопка «Открыть в новой вкладке» (`window.open(blobUrl, "_blank")`) и «Закрыть».
   - Гарантированный вызов `URL.revokeObjectURL` при закрытии окна.
4. **Диалог подтверждения удаления**:
   - Предупреждение о фиксации в журнале аудита.
   - Реактивное обновление списка вложений (`attachmentsResource.reload()`) и истории карточки (`onChanged()`) без перезагрузки страницы (SPA).

### R3. Тестирование и верификация (Definition of Done)
1. **Тесты в `backend/tests/test_attachments.py`**:
   - `test_attachment_preview_inline_header`: проверка заголовка `Content-Disposition: inline`.
   - `test_attachment_delete_success_and_audit_event`: проверка удаления с диска, из базы и наличия события `attachment_deleted` в `interaction_events`.
   - `test_attachment_delete_rbac_and_scope`: 152-ФЗ изоляция (404 для чужой карточки, 403 для неавтора без привилегий).
   - `test_attachment_delete_cas_optimistic_lock`: 409 Conflict при несовпадении `expected_revision`.
   - `test_attachment_delete_idempotency`: безопасный повтор по `Idempotency-Key`.
2. **Инварианты**:
   - Все 530+ тестов бэкенда проходят со 100% успехом.
   - Все 4 системных оракула (`verify_infra`, `verify_workflow`, `verify_reports`, `verify_plan`) — PASS.
   - `npx tsc --noEmit` и `npx vite build` — 0 ошибок.
   - `docs/architecture/` — строго 0 байт изменений (READ-ONLY).
   - Корневой `.env` отсутствует.

## Acceptance Criteria

### Backend & Security
- [ ] Параметр `disposition=inline` возвращает `Content-Disposition: inline`.
- [ ] `DELETE /interactions/{id}/attachments/{att_id}` удаляет файл с диска и запись из БД.
- [ ] В `interaction_events` создаётся событие `attachment_deleted` с метаданными файла.
- [ ] Попытка доступа к чужой карточке возвращает HTTP 404 (сокрытие факта существования).
- [ ] Удаление чужого файла рядовым менеджером возвращает HTTP 403 Forbidden.
- [ ] При несовпадении `expected_revision` возвращается HTTP 409 Conflict.
- [ ] Поддерживается `Idempotency-Key` с сохранением ответа.

### Frontend UI/UX
- [ ] В блоке вложений отображается кнопка «Просмотр» для PDF и изображений.
- [ ] Модальное окно предпросмотра отображает PDF в `iframe`, изображения в `img` без скачивания на диск.
- [ ] При закрытии модального окна вызывается `URL.revokeObjectURL`.
- [ ] Кнопка «Удалить» отображается для автора, руководителя и администратора.
- [ ] Диалог подтверждения предупреждает о записи в аудит и реактивно обновляет список файлов и таймлайн без перезагрузки страницы.

### Verification & Invariants
- [ ] Новые тесты в `backend/tests/test_attachments.py` проходят со 100% успехом.
- [ ] Полный сьют бэкенда (`pytest`) завершается с 0 failed (530+ passed).
- [ ] Все 4 оракула — PASS.
- [ ] Сборка фронтенда (`tsc` и `vite build`) — 0 ошибок.
- [ ] `docs/architecture/` — 0 изменений.


## 2026-09-26T20:55:00Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.
Прямое открытие предпросмотра вложений в новой вкладке браузера вместо модального окна: при нажатии на кнопку «Просмотр» файл (PDF, изображения) сразу открывается в новой вкладке (`window.open`), устраняя ошибку блокировки содержимого политикой безопасности CSP (`ERR_BLOCKED_BY_CSP`) во фрейме, с сохранением безопасного потокового доступа (`disposition=inline`), контроля прав и очистки ресурсов.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Интерфейс карточки взаимодействия (`frontend/src/views/InteractionPage.tsx`)
1. **Прямое открытие в новой вкладке по кнопке «Просмотр»**:
   - При нажатии на кнопку «Просмотр» в списке прикрепленных файлов исключить открытие модального окна предпросмотра с `iframe`.
   - Реализовать прямое открытие предпросмотра файла в новой вкладке браузера:
     * Для предотвращения блокировки всплывающих окон браузером открывать целевую вкладку (`window.open('about:blank', '_blank')`), запрашивать авторизованный Blob с `disposition=inline` через `api.previewAttachmentBlob(...)` и направлять вкладку на полученный `blobUrl`.
     * В случае ошибки загрузки информировать пользователя и безопасно закрывать открытую вкладку.
2. **Удаление модального окна предпросмотра**:
   - Удалить компонент `AttachmentPreviewModal` и связанное состояние предпросмотра из `InteractionPage.tsx`.
   - Модальное окно подтверждения удаления (`DeleteAttachmentModal`), кнопка «Скачать» и кнопка «Удалить» остаются полностью функциональными.

### R2. Безопасность и сохранение инвариантов
1. **Инварианты безопасности (152-ФЗ, CSP)**:
   - Просмотр остаётся авторизованным через API CRM с проверкой прав доступа к карточке (`scoped_interaction`).
   - Исключается ошибка `ERR_BLOCKED_BY_CSP`, так как файл открывается как документ в отдельном окне/вкладке браузера с нативным встроенным средством просмотра PDF/изображений.
   - Сохраняются все проверки удаления, CAS, `Idempotency-Key` и журнал аудита `attachment_deleted`.
2. **Тестирование и оракулы**:
   - Все существующие тесты бэкенда (542+ тестов) проходят со 100% успехом.
   - Все 4 системных оракула (`verify_infra`, `verify_workflow`, `verify_reports`, `verify_plan`) — PASS.
   - Сборка фронтенда (`npx tsc --noEmit && npx vite build`) — 0 ошибок.
   - `docs/architecture/` — строго 0 байт изменений (READ-ONLY).
   - Корневой `.env` отсутствует.

## Acceptance Criteria

### UI / UX
- [ ] При нажатии на кнопку «Просмотр» не появляется промежуточное модальное окно.
- [ ] Документ/изображение сразу открывается в новой вкладке браузера через нативный просмотрщик.
- [ ] Кнопки «Скачать» и «Удалить» продолжают работать штатно.

### Quality & Invariants
- [ ] `npx tsc --noEmit` и `npx vite build` завершаются с 0 ошибок.
- [ ] Все 4 системных оракула выдают PASS.
- [ ] Все 542+ теста бэкенда проходят со 100% успехом.
- [ ] `docs/architecture/` — 0 байт изменений.


## 2026-09-27T11:04:03Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Full team (Architect, Backend Developer, Frontend Developer, QA / Victory Auditor)

Use the full distributed team of agents (Architect, Backend Developer, Frontend Developer, QA / Victory Auditor) for end-to-end execution of all 4 stages.
Комплексное устранение замечаний повторного независимого аудита версии rost_crm5 и доведение требований ТЗ (ПАО «Ростелеком» / ЛЦТ 2026): закрытие уязвимостей разграничения доступа 152-ФЗ (R5-01, R5-05), внедрение исполнителя фоновых отчётов и эндпоинта скачивания (R5-02), обеспечение идемпотентности миграций Alembic (R5-03), исправление кириллицы и структуры PDF (R5-04), синхронизация DTO и вкладок отчётов (R5-06, R5-07, R5-13), надёжность интеграций (R5-08, R5-09, R5-15), целостность посещений и договоров (R5-10, R5-11, R5-12, R5-14), неблокирующий I/O файлов (R5-17), а также реализация назначения ответственного за вуз, пользовательского выбора колонок и динамического workflow.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Устранение критических уязвимостей безопасности и базовых сценариев (P1)
1. **R5-01 (Изоляция импорта организаций, `backend/app/importer.py`)**:
   - Запретить автоматическую выдачу/эскалацию прав `OrganizationAccess(read_all=True, can_create=True)` при совпадении названия с существующей организацией.
   - Обновление существующей организации требует предварительной проверки доступа (`has_organization_access(db, user, org.id)`). При отсутствии прав строка отклоняется/пропускается без выдачи доступа. Добавить регрессионный тест на попытку эскалации прав.
2. **R5-02 (Фоновые отчёты и воркер, `main.py`, `services.py`, `compose.yaml`)**:
   - Реализовать исполнение фоновых задач: периодический опрос очереди `queued` и вызов `process_background_job` (фоновый диспетчер в lifespan FastAPI при `BACKGROUND_WORKER_ENABLED=true` или отдельный воркер).
   - Пробросить `BACKGROUND_WORKER_ENABLED: "true"` в сервис `api` в `compose.yaml`.
   - Реализовать эндпоинт `GET /api/v1/jobs/{job_id}/download` для скачивания готового отчёта с проверкой прав `reports.read`, авторства `requester_id` и `authz_epoch`.
3. **R5-03 (Устойчивость миграций к существующей БД, `backend/alembic/versions/0001_initial_schema.py`)**:
   - Обеспечить идемпотентность первичной миграции на существующей базе через инспекцию схемы (`sa.inspect(op.get_bind())`) перед `create_table`, чтобы `alembic upgrade head` корректно инициализировал `alembic_version` без ошибки `relation already exists`.
4. **R5-04 (Кириллица и целостность генератора PDF, `backend/app/reports_export.py`)**:
   - Обеспечить корректное отображение русского языка: встраивание кириллического шрифта (Unicode TrueType с FontDescriptor / ToUnicode CMap).
   - Исправить синтаксис PDF-потока в блоке метаданных (открывать `BT` перед каждым выводом текста или закрывать `ET` после завершения блока).
   - Обеспечить перенос длинных строк без потери данных и корректный расчёт высоты строк.
5. **R5-05 (Область видимости администратора в миграциях workflow, `backend/app/services.py`)**:
   - Убрать безусловное исключение `if user.role != "administrator"` в `preview_workflow_migration` и `commit_workflow_migration`.
   - Применять `scope_clause(user)` ко всем ролям. Для глобальной миграции требовать явное разрешение `workflow.global_migrate` с фиксацией в аудите.

### R2. Устранение функциональных дефектов и расхождений контрактов (P2)
1. **R5-06 (Экспорт текущей вкладки, `frontend/src/views/Reports.tsx`)**:
   - Привязать состояние экспорта к активной вкладке: раздельное хранение параметров для `snapshot`, `activity`, `created`. В `handleExport` использовать параметры активного режима `mode`.
2. **R5-07 (Синхронизация контракта динамики переходов, `services.py`, `Reports.tsx`)**:
   - В функции `activity()` наполнить строки `selected_rows` полями `title`, `organization_name`, `owner_at_event_name`, `actor_name`.
   - Обновить TypeScript-типы и рендеринг таблицы в `Reports.tsx`.
3. **R5-08 & R5-09 (Надёжность live-интеграций и окружение, `live_lms.py`, `live_website.py`, `compose.yaml`)**:
   - Убрать подавление исключений (`return []`). Ошибки сети, 401, 500, таймауты и некорректный JSON должны фиксироваться со статусом `error` в журнале интеграций.
   - В `compose.yaml` пробросить переменные: `LMS_INTEGRATION_MODE`, `LMS_BASE_URL`, `LMS_API_TOKEN`, `WEBSITE_INTEGRATION_MODE`, `WEBSITE_BASE_URL`, `WEBSITE_API_TOKEN`.
4. **R5-10 (Двухфазный импорт с фиксацией пакета, `importer.py`)**:
   - Сохранять проверенный пакет на этапе preview с `import_id` и хэшем; на этапе commit подтверждать именно проверенный пакет.
   - Добавить парсер формата `.xls` (BIFF8).
5. **R5-11 & R5-12 (Синхронизация Visit ID и плана миграции, `services.py`)**:
   - Синхронизировать `Interaction.visit_id = new_visit.id` при создании взаимодействия и переходе этапа.
   - В миграции workflow фиксировать ревизии карточек на preview и валидировать их на commit с CAS-контролем.
6. **R5-13 (Фильтрация перед проверкой лимита отчёта, `services.py`)**:
   - В `snapshot()`, `activity()`, `created_report()` накладывать фильтры в SQL `WHERE` до проверки лимита 5000 карточек.
7. **R5-14 (Валидация Договор — Лицензия, `services.py`)**:
   - При наличии обоих полей проверять инвариант: `license.contract_id == interaction.contract_id`.
8. **R5-15 (Атомарность ревизий интеграций, `integrations/service.py`)**:
   - Добавить поле `last_applied_revision` в `LearningMetric` и обновлять атомарным CAS-запросом.
9. **R5-17 (Асинхронная неблокирующая загрузка файлов, `backend/app/main.py`)**:
   - Обернуть тяжелые синхронные вызовы `save_attachment` в `await anyio.to_thread.run_sync(...)`.

### R3. Доведение прямых требований ТЗ (Пользовательские сценарии)
1. **Назначение ответственного за вуз (ТЗ стр. 5)**:
   - Поддержать назначение, смену и снятие ответственного сотрудника за образовательную организацию руководителем/администратором в API и UI карточки организации.
2. **Пользовательский выбор колонок в отчётах (ТЗ стр. 4)**:
   - Добавить компонент выбора колонок (чекбоксы) в форме отчётов и передавать выбранные колонки в генераторы экспорта XLSX/PDF/JSON.
3. **Динамический Workflow в БД (ТЗ стр. 4–5)**:
   - Загрузка определений workflow из БД (`WorkflowVersion`) и визуализация/публикация версий.

### R4. Инварианты и контроль качества (Definition of Done)
1. `docs/architecture/` — строго 0 байт изменений (READ-ONLY).
2. 0 новых внешних npm/pip библиотек (Ponytail).
3. Все 543+ тестов бэкенда и новые регрессионные тесты проходят на 100%.
4. 4 системных оракула (`verify_infra`, `verify_workflow`, `verify_reports`, `verify_plan`) — PASS.
5. Сборка фронтенда (`tsc --noEmit && vite build`) — 0 ошибок.
6. Сгенерированный PDF содержит читаемый русский текст без квадратов.

## Acceptance Criteria

### Security & Invariants
- [ ] Импорт чужой организации не расширяет права пользователя (R5-01).
- [ ] Администратор без явного разрешения подчиняется `scope_clause` в миграциях (R5-05).
- [ ] Договор и лицензия проверяются на соответствие друг другу (R5-14).
- [ ] `docs/architecture/` содержит ровно 0 байт diff.

### Background Jobs & Reports
- [ ] Фоновые задачи отчётов реально выполняются и переходят в `succeeded` (R5-02).
- [ ] Эндпоинт `/jobs/{id}/download` отдаёт сформированный отчёт.
- [ ] Лимит 5000 проверяется после наложения фильтров (R5-13).
- [ ] Экспорт скачивает данные активной вкладки (R5-06).
- [ ] В таблице динамики отображаются название, вуз, исторический ответственный и инициатор (R5-07).
- [ ] PDF-отчёт отображает кириллицу корректно и читаемо (R5-04).
- [ ] Поддерживается выбор отображаемых колонок в отчёте.

### Integrations, Files & Data Integrity
- [ ] Сбои live-интеграций фиксируются со статусом `error`, переменные проброшены в compose (R5-08, R5-09).
- [ ] Обновление `LearningMetric` защищено от гонок ревизий (R5-15).
- [ ] Загрузка файлов не блокирует асинхронный event loop FastAPI (R5-17).
- [ ] `Interaction.visit_id` совпадает с `StateVisit.id` (R5-11).
- [ ] Поддержано назначение и снятие ответственного за организацию.

### Verification
- [ ] Все 543+ существующих тестов и новые тесты проходят (0 failed).
- [ ] Все 4 оракула — PASS.
- [ ] Сборка фронтенда — 0 ошибок.


## 2026-09-27T14:09:15Z

# Teamwork Project Prompt — Resume at Stage 2 (Frontend) & Stage 3 (QA / Victory Audit)

> Status: Resumed after orchestrator restart
> Goal: End-to-end execution of Stage 2 (Frontend) and Stage 3 (QA & Victory Audit)
> Requested team: Full team (Frontend Developer, QA / Victory Auditor)

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Integrity mode: development

## Status & Pre-requisites Already Completed:
1. **Stage 0 (Architect)**: Fully completed. Blueprint available at `.agents/architect_1/report.md`.
2. **Stage 1 (Backend Developer)**: Fully completed. Delivery report at `.agents/backend_1/handoff.md`.
   - All 17 audit items (R5-01 through R5-17) and R3 backend requirements implemented.
   - `backend/tests/test_final_delivery_r3_r5.py` created and passed (4/4 tests).
   - Full pytest suite: 547 passed, 1 skipped, 0 failed.
   - All 4 system oracles (`verify_infra`, `verify_workflow`, `verify_reports`, `verify_plan`): PASS.
   - Invariants strictly preserved: 0 bytes diff on `docs/architecture/`, 0 new pip/npm packages.

## Tasks to Execute:

### Stage 2: Frontend Implementation (Frontend Developer)
1. **`frontend/src/types.ts`**:
   - Align `ActivityRow`: add `title?: string`, `organization_name?: string`, `owner_at_event_name?: string`, `actor_name?: string`.
   - Add `owner_id?: string | null` to `Organization`.
   - Update report request types to include `selected_columns?: string[]`.
2. **`frontend/src/views/Reports.tsx`**:
   - **R5-06**: Separate filter/export state per tab (`snapshot`, `activity`, `created`). Ensure `handleExport` exports the active tab's data using active filters.
   - **R5-07**: Render transitions dynamic table with `title`, `organization_name`, `owner_at_event_name`, and `actor_name`.
   - **R3.2**: Column selection UI (checkboxes or toggle list) for choosing which columns to display and export.
3. **`frontend/src/views/CatalogPage.tsx` / `ReferenceViews.tsx`**:
   - **R3.1**: Manager assignment UI for Educational Organizations:
     * Display current assigned manager (`owner_id`).
     * Allow supervisors and administrators to assign, change, or remove the assigned manager via `PATCH /api/v1/organizations/{id}`.
4. **`frontend/src/views/WorkflowGraphView.tsx`**:
   - **R3.3**: Support dynamic workflow versions:
     * Fetch available versions from `GET /api/v1/workflow/versions`.
     * Allow selecting published workflow versions and rendering the graph (`/api/v1/workflow?version={v}`).
5. **Frontend Build Verification**:
   - Run `cd frontend && npm run build` (or `npx tsc --noEmit && npx vite build`) — must pass with 0 errors.

### Stage 3: Verification & Victory Audit (QA & Victory Auditor)
1. Run full backend test suite (`backend/.venv/bin/pytest backend/tests/ -q`) — ensure 547+ passed, 0 failed.
2. Run all 4 system oracles:
   - `python3 docs/checks/verify_infra.py`
   - `python3 docs/checks/verify_workflow.py`
   - `python3 docs/checks/verify_reports.py`
   - `python3 docs/checks/verify_plan.py`
3. Verify frontend build passes cleanly.
4. Verify Cyrillic text rendering in generated PDF reports.
5. Generate the authoritative Victory Audit Report covering all 17 audit items and R3 requirements.


## 2026-09-27T20:07:22Z

# Teamwork Project Prompt — Draft

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.

Рефакторинг ленты истории решений, введение табов для разделения комментариев и этапов процесса, удаление избыточных канцеляризмов из диалога удаления файлов и сокрытие технических записей `attachment_deleted` в пользовательском интерфейсе `frontend/src/views/InteractionPage.tsx`.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Очистка диалога удаления вложений (`DeleteAttachmentModal`)
- В компоненте `DeleteAttachmentModal` (`frontend/src/views/InteractionPage.tsx`) удалить блок с предупреждением о 152-ФЗ / журнале аудита.
- Оставить лаконичный текст подтверждения:
  `Вы действительно хотите удалить файл «{attachment.file_name}» ({formatFileSize(attachment.file_size)})? Это действие нельзя отменить.`
- Сохранить кнопку удаления и обработчик без изменений.

### R2. Фильтрация технического аудита удаления в пользовательской ленте
- Исключить отображение системных записей аудита с типом `attachment_deleted` из бизнес-таймлайна решений в карточке взаимодействия.
- Бэкенд-логирование удаления файлов в PostgreSQL (`backend/app/files.py`) оставить неизменным (инвариант 152-ФЗ / аудит-след).

### R3. Вкладки разделения комментариев и истории этапов (Timeline Tabs)
- В `InteractionPage.tsx` добавить локальное состояние активной вкладки:
  `const [historyTab, setHistoryTab] = useState<'all' | 'comments' | 'stages'>('all');`
- Классифицировать события ленты:
  - **Комментарии (`commentsList`)**: записи типов `comment_added`, `comment`, а также `standaloneComments` карточки.
  - **Этапы workflow (`stagesList`)**: переходы процесса (`stage_transition`, `state_changed`, `assignment_changed`).
  - **Все (`allList`)**: полный объединенный список за вычетом технических `attachment_deleted`.
- В шапке секции `timeline-panel` разместить аккуратные кнопки-переключатели с бейджами/счётчиками количества элементов:
  - «Все» (с общим счетчиком `allList.length`);
  - «Комментарии» (со счетчиком `commentsList.length`);
  - «Этапы workflow» (со счетчиком `stagesList.length`).
- При отсутствии записей в выбранной категории отображать плейсхолдер:
  `<p className="empty-inline">В этой категории пока нет записей.</p>`.
- Стили переключателей должны гармонично использовать существующую дизайн-систему (Gen2, Ponytail — без добавления новых классов стилей).

## Acceptance Criteria

### UI & UX Quality
- [ ] В модальном окне удаления вложений отсутствует канцеляритный блок с предупреждением о 152-ФЗ.
- [ ] В ленте решений не отображаются записи типа `attachment_deleted`.
- [ ] Переключение между табами «Все», «Комментарии», «Этапы workflow» фильтрует ленту без перезагрузки страницы (SPA).
- [ ] Счетчики на вкладках корректно отображают количество соответствующих событий.
- [ ] При пустой выборке выводится плейсхолдер `<p className="empty-inline">В этой категории пока нет записей.</p>`.

### Invariants & Verification
- [ ] Сборка фронтенда `npm run build` в `frontend/` проходит без ошибок компиляции TypeScript (0 errors).
- [ ] Тесты бэкенда `backend/.venv/bin/pytest backend/tests/test_working_slice.py` проходят на 100% (0 failed).
- [ ] Директория `docs/architecture/` строго не изменена (0 байт diff).
- [ ] 0 новых сторонних npm или pip пакетов (Ponytail Ladder).

## 2026-09-27T22:35:37Z

# Teamwork Project Prompt — Launched

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.

Реализация строгого ролевого разграничения видимости вкладок на странице «База знаний и регламенты» (`HelpPage`) в `frontend/src/views/ReferenceViews.tsx` по принципу Need-to-Know и защита от несанкционированного рендеринга контента других должностей.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Ролевая фильтрация кнопок вкладок (`.help-tabs`)
- В компоненте `HelpPage` (`frontend/src/views/ReferenceViews.tsx`) разграничить отображение кнопок вкладок в соответствии с ролью текущего авторизованного пользователя (`me.role`):
  - Вкладка **«Администратор»**: отображать **только** пользователям с ролью `administrator` или `admin`.
  - Вкладка **«Руководитель»**: отображать **только** пользователям с ролью `supervisor`, `administrator` или `admin` (руководитель и администратор).
  - Вкладка **«Менеджер»**: отображать для всех трёх ролей (`manager`, `supervisor`, `administrator`/`admin`).
  - Вкладки **«Справочник ошибок»** и **«Безопасность 152-ФЗ»**: сквозные общесистемные разделы, отображаются для всех ролей без ограничений.

### R2. Guard-защита содержимого и валидация активного таба
- Реализовать предикат проверки доступности вкладки для заданной роли (например, `isHelpTabAllowed(tab, role)`).
- Обеспечить автоматический сброс активной вкладки на роль пользователя по умолчанию (`getInitialTab`), если текущее состояние `activeTab` указывает на недоступную для его роли вкладку (защита от ручной модификации состояния в DevTools или передачи невалидных параметров).
- В условном рендеринге содержимого вкладок добавить guard-проверку прав: контент вкладки «Администратор» не должен рендериться при отсутствии прав администратора, контент вкладки «Руководитель» — при отсутствии прав руководителя/администратора.

### R3. Сохранение функциональности тренажёра ошибок (AC21)
- Сохранить в полном объёме интерактивный симулятор обработки ошибок HTTP 409/422/413/Quarantine и проверки сохранения пользовательского ввода без сброса формы во вкладке «Справочник ошибок».

## Verification Resources
- Файл компонента: `frontend/src/views/ReferenceViews.tsx`.
- Тестовые контракты:
  - `npm run build` в каталоге `frontend/` (проверка типов TypeScript и чистоты бандла).
  - Новый юнит/контрактный тест бэкенда/фронтенда: `backend/tests/test_swe25_knowledge_base_role_tabs.py` (статический и контрактный анализ разграничения ролей вкладок и guard-проверок).
  - Регрессионный срез: `backend/.venv/bin/pytest backend/tests/test_working_slice.py`.
  - Системные оракулы: `python3 docs/checks/verify_infra.py`.

## Acceptance Criteria

### UI & Access Control
- [ ] Пользователь с ролью `manager` видит ровно 3 вкладки («Менеджер», «Справочник ошибок», «Безопасность 152-ФЗ») и не видит вкладок «Руководитель» и «Администратор».
- [ ] Пользователь с ролью `supervisor` видит ровно 4 вкладки («Руководитель», «Менеджер», «Справочник ошибок», «Безопасность 152-ФЗ») и не видит вкладки «Администратор».
- [ ] Пользователь с ролью `administrator` / `admin` видит все 5 вкладок.
- [ ] Начальная вкладка по умолчанию открывается в соответствии с ролью: `manager` для менеджера, `supervisor` для руководителя, `admin` для администратора.
- [ ] При попытке активации недоступной вкладки контент не рендерится, происходит корректный fallback на доступную вкладку.
- [ ] Тренажёр проверки сохранения ввода при ошибках (AC21) во вкладке «Справочник ошибок» полностью сохраняет свою работоспособность.

### Invariants & Verification
- [ ] Сборка фронтенда `npm run build` в `frontend/` проходит с 0 ошибок компиляции TypeScript.
- [ ] Обновлённый бандл скопирован в рабочий Docker-контейнер `rtk-crm-frontend-1` с мягким релоадом Nginx (`nginx -s reload`).
- [ ] Тесты `backend/tests/test_working_slice.py` и новый контрактный тест `test_swe25_knowledge_base_role_tabs.py` проходят на 100% (0 failed).
- [ ] Системный оракул `python3 docs/checks/verify_infra.py` проходит со статусом PASS.
- [ ] Каталог `docs/architecture/` строго READ-ONLY (0 байт diff).
- [ ] 0 новых сторонних npm или pip пакетов (Ponytail Ladder).


## 2026-09-28T18:44:40Z

# Teamwork Project Prompt — Launched

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Engineering Review, Ponytail Guardian & Quality Assurance Team

Комплексный аудит, ревизия кода на предмет оверинжиниринга (Ponytail), проверка соответствия 152-ФЗ, валидация фронтенда/бэкенда и устранение выявленных замечаний по выполненной задаче SWE-26 (Deliveries API, UI поставок в карточке взаимодействия, панель лицензий в справочниках).

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Ревизия на оверинжиниринг и чистоту кода (Ponytail Review)
- Провести аудит изменений в файлах `backend/app/services.py`, `backend/app/main.py`, `backend/app/schemas.py`, `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/views/InteractionPage.tsx`, `frontend/src/views/CatalogPage.tsx`.
- Выявить и устранить любые избыточные абстракции, дублирование логики, неиспользуемые импорты или избыточный код в соответствии с принципами «Лестницы» (The Ladder) и правилом минимального diff.
- Проверить переиспользование существующих стилей Gen2 Light Theme без создания дублирующих классов.

### R2. Контроль безопасности и инвариантов 152-ФЗ / ФСТЭК №117
- Проверить строгое сокрытие чужих карточек взаимодействий и связанных поставок (чужой `interaction_id` обязан возвращать HTTP 404 Not Found, не раскрывая факт существования записи).
- Убедиться, что эндпоинты поставок не позволяют несанкционированно привязывать лицензии или контакты сторонних организаций.
- Проверить корректность CAS-проверки (`expected_revision`) и обработку заголовка `Idempotency-Key` (защита от повторных списаний/поставок).

### R3. Проверка функциональности и контрактов API
- Проверить корректность эндпоинтов:
  * `GET /api/v1/interactions/{interaction_id}/deliveries`
  * `POST /api/v1/interactions/{interaction_id}/deliveries`
- Проверить фиксацию неизменяемого события `delivery_recorded` в `InteractionEvent` и его корректное отображение в таймлайне решений.
- Проверить интеграцию списка поставок в эндпоинт детальной карточки `GET /api/v1/interactions/{id}` (`detail`).

### R4. Проверка веб-интерфейса и реактивности (SPA)
- Проверить секцию «Выдача ПО и лицензий (Поставки)» в `InteractionPage.tsx`:
  * Корректность отображения пустого состояния («Выдача ПО пока не регистрировалась»).
  * Работу модального окна `RegisterDeliveryModal` (валидация обязательных полей, фильтрация контактов и лицензий только текущей организации).
  * Реактивное обновление таблицы поставок и таймлайна без перезагрузки всей страницы в браузере (SPA).
- Проверить панель «Лицензии ПО» в `CatalogPage.tsx` (корректность сопоставления с `products`, бейджи статусов передачи и сроки действия).

### R5. Устранение любых выявленных дефектов (Remediation)
- При обнаружении любых ошибок, неточностей, лишних строк кода или оверинжиниринга — внести точечные исправления непосредственно в кодовую базу.

## Verification Resources
- Набор тестов API и моделей: `backend/tests/test_swe26_deliveries_api.py`, `backend/tests/test_deliveries_models.py`, `backend/tests/test_working_slice.py`.
- Полный тестовый сьют: `backend/.venv/bin/pytest backend/tests/`.
- Системные оракулы:
  * `python3 docs/checks/verify_infra.py`
  * `python3 docs/checks/verify_workflow.py`
  * `python3 docs/checks/verify_reports.py`
  * `python3 docs/checks/verify_plan.py`
- Сборка фронтенда: `npm run build` в `frontend/`.
- Архитектурная документация: `docs/planning/adr/003-deliveries-api-and-license-transfer.md`.

## Acceptance Criteria

### Качество кода и Ponytail
- [ ] Отсутствуют избыточные конструкции, неиспользуемые переменные, дублирующийся код и надуманные абстракции.
- [ ] 0 новых сторонних зависимостей в `frontend/package.json` и `backend/requirements.txt`.
- [ ] Директория `docs/architecture/` строго не изменена (`git diff docs/architecture/` равен 0 байт).

### Безопасность и 152-ФЗ
- [ ] Доступ к чужим поставкам или карточкам возвращает строгий HTTP 404 Not Found (Zero-Oracle).
- [ ] При создании поставки валидируется принадлежность лицензии и контакта к организации карточки.
- [ ] CAS-защита и идемпотентность функционируют корректно.

### Тестирование и сборка
- [ ] Сборка фронтенда `npm run build` проходит без единой ошибки TypeScript (0 errors).
- [ ] Все 4 системных оракула (`verify_infra`, `verify_workflow`, `verify_reports`, `verify_plan`) возвращают статус PASS.
- [ ] Все тесты в `backend/tests/` (563+ тестов) проходят со 100% успехом (0 failed).
- [ ] Обновленные файлы синхронизированы с рабочими Docker-контейнерами `rtk-crm-api-1` и `rtk-crm-frontend-1`.


## 2026-09-28T20:02:01Z

# Teamwork Project Prompt — Launched

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Security Auditor, Backend Inspector, Frontend/Browser QA & Victory Auditor

Глубокий, беспристрастный 4-шаговый аудит проекта `rost_crm` по пятому функциональному домену: загрузка, валидация и безопасное хранение файлов-вложений, потоковая интеграция с антивирусом ClamAV, изоляция доступа к скачиванию (152-ФЗ / ФСТЭК №117, Zero-Oracle 404) и неудаляемый журнал аудита операций.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Аудит бэкенда, БД и валидации файлов (Files & ClamAV Engine)
- Проверить модель `Attachment` в `backend/app/models.py` и модуль `backend/app/files.py`:
  * Список строго 10 разрешённых расширений: `png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx` (плюс алиасы `jpg, gz`).
  * Проверка жесткого лимита размера файла: ровно 25 МБ (26 214 400 байт), отказ с кодом HTTP 413 `FILE_TOO_LARGE`.
  * Валидация сигнатур (magic bytes) и блокировка исполняемых/опасных форматов (PE EXE/DLL `MZ`, ELF, PHP, `<script`, Mach-O) с кодом HTTP 422 `FILE_TYPE_NOT_ALLOWED`.
  * Санитизация имени файла (защита от path traversal, относительных путей `..` и нулевых байтов ` `).
  * Потоковая интеграция со сканером ClamAV (`scan_clamav_stream` по протоколу zINSTREAM на порт 3310). Корректная обработка сигнатур `FOUND` (HTTP 422 `VIRUS_DETECTED`) и отказоустойчивость при недоступности демона (HTTP 503 `ANTIVIRUS_UNAVAILABLE`).
- Проверить эндпоинты в `backend/app/main.py`:
  * `POST /api/v1/interactions/{id}/attachments` (загрузка с расчётом SHA-256, поддержкой CAS `expected_revision` и `Idempotency-Key`).
  * `GET /api/v1/interactions/{id}/attachments` (список вложений карточки).
  * `GET /api/v1/interactions/{id}/attachments/{att_id}/download` (скачивание с проверкой прав, заголовком Content-Disposition и inline-preview).
  * `DELETE /api/v1/interactions/{id}/attachments/{att_id}` (удаление файла с проверкой CAS, ролей и записью в `InteractionEvent`).

### R2. Инварианты безопасности 152-ФЗ, ФСТЭК №117 и аудит
- Проверить Zero-Oracle изоляцию: попытка прямого запроса чужого файла/карточки (`scoped_interaction`) обязана возвращать строгий HTTP 404 Not Found (не раскрывая факт существования записи).
- Проверить запрет прямых публичных ссылок: скачивание строго через авторизованный эндпоинт с проверкой JWT токена текущего пользователя.
- Проверить фиксацию неизменяемых событий аудита:
  * При загрузке файла фиксируется `attachment_uploaded` с указанием `attachment_id`, `file_name`, `file_size`, `checksum`.
  * При удалении файла фиксируется `attachment_deleted` с сохранением метаданных удалённого файла.

### R3. Статический и компонентный аудит фронтенда (`InteractionPage.tsx`)
- В компоненте `frontend/src/views/InteractionPage.tsx`:
  * Блок «Файлы и документы»: отображение таблицы вложений, размера, даты, автора и бейджей статусов.
  * Модальное окно загрузки: drag-and-drop зона, валидация допустимых типов на клиенте, индикация прогресса.
  * Модальное окно предпросмотра (`PreviewModal`): безопасный просмотр PDF и картинок (`image/png`, `image/jpeg`) без принудительного сохранения на диск.
  * Модальное окно удаления (`DeleteAttachmentModal`): подтверждение удаления без сброса формы и без канцелярских блоков.
  * Реактивность SPA: добавление и удаление вложений обновляет список реактивно без перезагрузки всей страницы в браузере.

### R4. Сквозное интерактивное тестирование (E2E Browser & Adversarial)
- Провести тестирование в реальном браузере через субагента `browser` на стенде `http://localhost:3000`:
  * Под `manager-a` («Анна Смирнова»): загрузка валидного файла (PDF/PNG), скачивание, предпросмотр, удаление с проверкой появления события в таймлайне.
  * Попытка загрузки вредоносного файла / EICAR сигнатуры: фиксация блокировки антивирусом ClamAV.
  * Под `manager-b` («Михаил Волков»): проверка сокрытия по 152-ФЗ при попытке прямого обращения к вложению менеджера А (строгий HTTP 404).
  * Проверка локальных хранилищ браузера (`localStorage`, `sessionStorage`): подтверждение отсутствия JWT-токенов в веб-хранилищах (только in-memory).

### R5. Устранение выявленных дефектов (Remediation) и итоговый отчёт
- При обнаружении любых ошибок валидации, уязвимостей, регрессий или несоответствий ТЗ — внести минимальные точечные исправления в кодовую базу в соответствии с принципами Ponytail.
- Сформировать подробный отчёт с матрицей покрытия (R10, R11, R27, B17, B18, B19, AC16, AC17, AC22).

## Verification Resources
- Наборы тестов вложений и ClamAV:
  * `backend/tests/test_attachments.py` (40 тестов)
  * `backend/tests/test_clamav.py` (26 тестов)
  * Регрессионный срез: `backend/tests/test_working_slice.py` (17 тестов)
- Системные оракулы:
  * `python3 docs/checks/verify_infra.py` (проверка Docker ClamAV, Nginx 25MB, volumes)
  * `python3 docs/checks/verify_workflow.py`
  * `python3 docs/checks/verify_reports.py`
  * `python3 docs/checks/verify_plan.py`
- Сборка фронтенда: `cd frontend && npm run build` (0 TypeScript errors)
- Работающий стек Docker: `rtk-crm-clamav-1` (порт 3310), `rtk-crm-api-1`, `rtk-crm-frontend-1`

## Acceptance Criteria

### Валидация и безопасность файлов (R10, R11, R27)
- [ ] Разрешены ровно 10 расширений из ТЗ: `png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx` (и алиасы `jpg, gz`); все остальные отклоняются с кодом 422.
- [ ] Файлы размером > 25 МБ отклоняются с кодом 413 `FILE_TOO_LARGE`.
- [ ] Опасные исполняемые файлы (PE EXE, ELF, скрипты) блокируются по magic bytes даже при подмене расширения (422).
- [ ] Сигнатура EICAR / вирусы блокируются ClamAV с кодом 422 `VIRUS_DETECTED`.
- [ ] Запросы чужих файлов/карточек возвращают строго HTTP 404 Not Found (Zero-Oracle).
- [ ] При удалении файла генерируется неизменяемое событие `attachment_deleted` в `InteractionEvent`.

### Пользовательский интерфейс и E2E
- [ ] Загрузка, предпросмотр и удаление вложений работают без перезагрузки всей страницы браузера (SPA).
- [ ] Удаление файла требует подтверждения в модальном окне и реактивно удаляет карточку файла из списка.
- [ ] JWT-токены не сохраняются в `localStorage` или `sessionStorage` (152-ФЗ / ФСТЭК №117).

### Инварианты репозитория и качество
- [ ] Все тесты `test_attachments.py` и `test_clamav.py` (66 тестов) проходят со 100% успехом.
- [ ] Регрессионный срез `test_working_slice.py` проходит со 100% успехом.
- [ ] Все 4 системных оракула (`verify_infra`, `verify_workflow`, `verify_reports`, `verify_plan`) возвращают PASS.
- [ ] Сборка фронтенда `npm run build` проходит с 0 ошибок TypeScript.
- [ ] Директория `docs/architecture/` строго не изменена (0 байт diff).
- [ ] 0 новых сторонних зависимостей в `requirements.txt` и `package.json`.

## 2026-09-28T20:58:44Z

# Teamwork Project Prompt — Launched

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Audit & Verification Team (Backend, Security 152-FZ, Frontend/Browser QA & Victory Auditor)

Глубокий, беспристрастный 4-шаговый аудит проекта `rost_crm` по шестому функциональному домену: ведение хронологической ленты «История решений», разделение типов событий (все события, комментарии, переходы), неизменяемый аудит-лог (152-ФЗ / ФСТЭК №117) и механизм фиксации заметок сотрудников.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Аудит бэкенда, моделей и неизменяемого журнала событий (Event Journal & Comments)
- Проверить модель `InteractionEvent` и `Comment` в `backend/app/models.py`:
  * Наличие полей: первичный ключ UUID (`id`), внешний ключ `interaction_id`, тип события `type` (`initial_state`, `state_changed`, `owner_changed`, `comment_added`, `attachment_uploaded`, `attachment_deleted`, `delivery_recorded`), `user_id`, метка времени `effective_at`, монотонно возрастающий порядковый номер `sequence`, `payload` (JSONB) и строковые атрибуты (`from_state`, `to_state`, `comment`, `file_name`, и др.).
- Проверить сервисные функции в `backend/app/services.py`:
  * `append_event`: строго атомарная вставка в `InteractionEvent` с автоматическим инкрементом `sequence` и ревизии `revision`. Запрет модификации или удаления существующих записей (immutable audit log).
  * `add_comment`: проверка прав доступа (`interactions.comment`), проверка области доступа к взаимодействию (`scoped_interaction`), валидация непустого текста заметки, атомарное создание `Comment` и фиксация события `comment_added` в таймлайне.
- Проверить эндпоинты в `backend/app/main.py`:
  * `POST /api/v1/interactions/{id}/comments` (добавление комментария с CAS-проверкой `expected_revision` и `Idempotency-Key`).
  * `GET /api/v1/interactions/{id}` (отдача упорядоченного массива событий `history` и `comments`).
  * `GET /api/v1/interactions/{id}/history` (при наличии отдельного эндпоинта).

### R2. Инварианты безопасности 152-ФЗ, ФСТЭК №117 и ролевая изоляция
- Zero-Oracle сокрытие: запрос чужих событий, карточек или комментариев (`scoped_interaction`) обязан возвращать строгий HTTP 404 Not Found (не раскрывая факт существования карточки).
- Неизменяемость истории: отсутствие эндпоинтов или методов `UPDATE` / `DELETE` для сущностей `InteractionEvent` и `Comment`.
- Защита от подделки авторства: поле `user_id` заполняется строго из проверенного JWT-токена сессии текущего пользователя.

### R3. Статический и компонентный аудит фронтенда (`InteractionPage.tsx`)
- В компоненте `frontend/src/views/InteractionPage.tsx`:
  * Блок «История решений» (`События и комментарии`):
    - Вкладки фильтрации: **«Все»**, **«Комментарии»**, **«Этапы workflow»**.
    - Корректность динамических счетчиков событий на кнопках вкладок.
    - Корректность фильтрации: во вкладке «Комментарии» отображаются только текстовые заметки (`comment_added` / `comment`), во вкладке «Этапы workflow» — переходы этапов и смена ответственного, во вкладке «Все» — полная хронология.
  * Панель добавления комментария (`side-panel`):
    - Текстовое поле ввода заметок с ограничением по символам (5000) и плейсхолдером.
    - Блокировка кнопки «Добавить комментарий» при пустом вводе или в процессе отправки (`busy`).
    - Очистка текстового поля после успешной отправки.
    - Реактивное обновление ленты и счетчиков вкладок без перезагрузки всей страницы браузера (SPA).

### R4. Сквозное интерактивное тестирование в браузере (E2E Browser Testing)
- Провести тестирование в реальном браузере через субагента `browser` на стенде `http://localhost:3000`:
  * Под `manager-a` («Анна Смирнова»):
    - Открыть карточку своего взаимодействия.
    - Переключить вкладку таймлайна на «Комментарии» — убедиться, что отображаются только заметки.
    - Добавить новый комментарий (например, «Аудит этапа 6: проверка добавления заметки менеджером») — проверить мгновенное появление в списке и очистку формы.
    - Переключить на «Этапы workflow» — убедиться, что добавленный текстовый комментарий не отображается в этой вкладке.
    - Переключить на «Все» — убедиться, что комментарий отображается в общей хронологии с указанием автора, даты и времени.
    - Выполнить переход по этапу (с обязательным комментарием, если требуется) или загрузить тестовый файл — убедиться в появлении соответствующей записи в ленте событий.
  * Проверка локальных хранилищ браузера (`localStorage`, `sessionStorage`): подтверждение отсутствия JWT-токенов в веб-хранилищах (только in-memory).

### R5. Устранение выявленных дефектов (Remediation) и итоговый отчёт
- При обнаружении любых ошибок фильтрации, верстки, сброса форм или нарушения принципов 152-ФЗ — внести минимальные точечные исправления в соответствии с принципами Ponytail.
- Сформировать подробный отчёт с матрицей покрытия (R05, R09, R14, R27, B04, B09, B20, AC08, AC22).

## Verification Resources
- Набор тестов таймлайна, комментариев и событий:
  * `backend/tests/test_swe24_timeline_tabs_and_attachment_cleanup.py` (4 теста)
  * `backend/tests/test_working_slice.py` (17 тестов)
- Системные оракулы:
  * `python3 docs/checks/verify_infra.py`
  * `python3 docs/checks/verify_workflow.py`
  * `python3 docs/checks/verify_reports.py`
  * `python3 docs/checks/verify_plan.py`
- Сборка фронтенда: `cd frontend && npm run build` (0 TypeScript errors)
- Контейнеры: `rtk-crm-api-1`, `rtk-crm-frontend-1`

## Acceptance Criteria

### Хронология и неизменяемость (R05, R09, R14, R27)
- [ ] Все события (`state_changed`, `owner_changed`, `comment_added`, `attachment_uploaded`, `attachment_deleted`, `delivery_recorded`) фиксируются в неизменяемом журнале `InteractionEvent` с последовательным `sequence`.
- [ ] Отсутствуют методы изменения или удаления событий истории (immutable audit log).
- [ ] Попытка запроса чужих событий или комментариев возвращает строго HTTP 404 Not Found (Zero-Oracle).
- [ ] Переход на этапы с требованием комментария (отмена, возврат) отклоняется без указания комментария.

### Пользовательский интерфейс и E2E (B20, AC08, AC22)
- [ ] Вкладки ленты решений («Все», «Комментарии», «Этапы workflow») корректно фильтруют записи и отображают точные счетчики.
- [ ] Форма комментария валидирует непустой ввод, блокирует кнопку при отправке и очищает поле после сохранения.
- [ ] Добавление комментария и переходы этапов обновляют ленту реактивно без перезагрузки всей страницы браузера (SPA).
- [ ] JWT-токены не сохраняются в `localStorage` или `sessionStorage` (152-ФЗ / ФСТЭК №117).

### Инварианты репозитория и качество
- [ ] Все тесты `test_swe24_timeline_tabs_and_attachment_cleanup.py` и `test_working_slice.py` проходят со 100% успехом.
- [ ] Все 4 системных оракула возвращают PASS.
- [ ] Сборка фронтенда `npm run build` проходит с 0 ошибок TypeScript.
- [ ] Директория `docs/architecture/` строго не изменена (0 байт diff).
- [ ] 0 новых сторонних зависимостей в `requirements.txt` и `package.json`.



## 2026-09-29T01:27:59Z

# Teamwork Project Prompt — Launched

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Ведущий системный архитектор, DevSecOps-инженер, Руководитель команды приёмки, Victory Auditor

Финальный, исчерпывающий и бескомпромиссный аудит и верификация всего проекта «ИТ Школа Ростелекома — CRM» (rost_crm) по Этапу 10: «Финальная интеграция, DevSecOps, Нагрузочные испытания (B31), Аудит ИБ (B33) и Верификация конкурсного комплекта сдачи (B39/B40)» в строгом соответствии с ТЗ (разделы 4, 6, 7, 8, 10), 149-ФЗ, 152-ФЗ, Приказом ФСТЭК № 117 и философией Ponytail.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Инфраструктурный аудит и DevSecOps (B32, B33, ТЗ разд. 4, 6)
- Проверить состояние Docker Compose стека (`docker compose ps`):
  * Все 6 контейнеров (`rtk-crm-frontend-1`, `rtk-crm-api-1`, `rtk-crm-keycloak-1`, `rtk-crm-clamav-1`, `rtk-crm-postgres-1`, `rtk-crm-redis-1`) находятся в состоянии Up (healthy).
- Проверить сетевую изоляцию:
  * Сеть `backend_net` имеет директиву `internal: true`. Контейнеры СУБД, Redis и ClamAV не имеют открытых наружу портов в глобальную сеть.
- Проверить конфигурацию Nginx (`deploy/nginx.conf`):
  * Лимит тела запроса: `client_max_body_size 25m;`.
  * Сжатие Gzip для текстовых ответов от 1024 байт.
  * Сквозной заголовок `X-Request-ID` и заголовки безопасности (CSP, `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`).
- Проверить пробы жизнеспособности:
  * `http://localhost:3000/health/live` -> 200 OK.
  * `http://localhost:3000/health/ready` -> 200 OK (`{"status":"ok","database":"ok"}`).
- Проверить чистоту Git-репозитория от секретов:
  * В `.env.example` и коде отсутствуют реальные боевые пароли и ключи.
- Проверить запуск от non-root:
  * Контейнеры запускаются от непривилегированного пользователя `appuser:10001` и `nginx`.

### R2. Нагрузочные испытания и бенчмарки (B31, R18, R19, AC30)
- Верифицировать нагрузочные испытания и отчёт `docs/benchmarks/load-test-report.md`:
  * 50 активных пользователей (конкурентные сессии): p95 < 500 мс (фактически зафиксировано ~48 мс, 0% ошибок при 10 000 req).
  * 10 одновременных тяжелых отчётов (Snapshot / Activity): среднее время генерации < 2 с (фактически ~312 мс).
  * Потоковое антивирусное сканирование: пропускная способность > 50 МБ/с без зависания очередей.

### R3. Проверка конкурсного комплекта сдачи (B39, B40, ТЗ раздел 10)
- Подтвердить наличие, комплектность и валидность всех 4 артефактов сдачи:
  1. **Репозиторий:** чистый код, оформленный `README.md` с бейджами, C4-архитектурой, инструкциями быстрого старта и демонстрационными учётными записями.
  2. **Презентация проекта:**
     - `docs/Презентация_CRM_ИТ_Школа_Ростелеком.pdf` (12 слайдов A4 Landscape в фирменном стиле Rostelecom Gen2 Light/Dark).
     - `docs/Презентация_CRM_ИТ_Школа_Ростелеком.html` (интерактивная HTML-версия).
  3. **Прототип и инструкция развёртывания:**
     - `docs/PROTOTYPE_DEPLOYMENT_GUIDE.md` (руководство запуска на VPS, Cloudflare Tunnel HTTPS, учетные данные ролей, 6-шаговый пользовательский сценарий).
  4. **Сопроводительная документация и пояснительная записка:**
     - `docs/Пояснительная_записка_и_сопроводительная_документация_CRM_ИТ_Школа_Ростелеком.pdf` (29 страниц, титульный лист, C4, ArchiMate 3.1, методы D01–D16, User Guide, Admin Guide, реестр библиотек, нагрузочный отчёт).
     - `docs/Пояснительная_записка_и_сопроводительная_документация_CRM_ИТ_Школа_Ростелеком.docx` (редактируемый файл Word).
     - `docs/Пояснительная_записка_и_сопроводительная_документация_CRM_ИТ_Школа_Ростелеком.md` (Markdown-исходник).
     - Архитектурные модели Archi: `docs/architecture/rtk-crm.archimate.xml` и `rost_crm_architecture.archimate`.

### R4. Контрольные независимые прогоны тестов и оракулов
- Запустить 4 системных оракула:
  * `python3 docs/checks/verify_infra.py`
  * `python3 docs/checks/verify_workflow.py`
  * `python3 docs/checks/verify_reports.py`
  * `python3 docs/checks/verify_plan.py`
  Все оракулы обязаны вернуть PASS.
- Запустить полный набор тестов Pytest:
  * `backend/.venv/bin/pytest backend/tests/ -q` (все тесты обязаны пройти со статусом PASSED, 0 failed).
- Запустить сборку фронтенда:
  * `cd frontend && npm run build` (0 ошибок TypeScript).

### R5. Финальный протокол сдачи (Victory Audit)
- Независимый аудитор победы формирует итоговый протокол приёмки всей CRM-системы (Этапы 1–10).
- Зафиксировать вердикт VICTORY CONFIRMED в `.agents/teamwork/victory_auditor_d10/audit_report.md` и `.agents/teamwork/handoff.md`.

## Verification Resources
- Набор системных оракулов: `docs/checks/verify_*.py`
- Полный каталог тестов: `backend/tests/` (125+ тестов)
- Нагрузочный отчёт: `docs/benchmarks/load-test-report.md`
- Комплект сдачи: каталоги `docs/` и `deploy/`
- Живой стек: `docker compose ps` на `localhost:3000` и `127.0.0.1:8000`

## Acceptance Criteria

### Инфраструктура и DevSecOps (B32, B33)
- [ ] Все 6 контейнеров находятся в статусе Up (healthy).
- [ ] Сеть `backend_net` изолирована (`internal: true`), СУБД/Redis/ClamAV закрыты от внешнего мира.
- [ ] Nginx обеспечивает лимит 25 МБ, Gzip, X-Request-ID, security headers.
- [ ] Пробы `/health/live` и `/health/ready` возвращают 200 OK.
- [ ] Контейнеры запускаются от non-root (`appuser:10001`, `nginx`).

### Нагрузочные испытания (B31, R18, R19, AC30)
- [ ] p95 время отклика при 50 параллельных сессиях < 500 мс.
- [ ] Время генерации тяжелых отчётов (Snapshot/Activity) < 2 с.
- [ ] Пропускная способность ClamAV потока > 50 МБ/с.

### Комплект конкурсной сдачи (B39, B40, ТЗ разд. 10)
- [ ] Репозиторий и `README.md` содержат актуальные инструкции, бейджи и учётные записи.
- [ ] Презентация проекта доступна в форматах PDF (12 слайдов Landscape) и HTML.
- [ ] Руководство развёртывания `docs/PROTOTYPE_DEPLOYMENT_GUIDE.md` проверено и актуально.
- [ ] Пояснительная записка доступна в PDF (29 страниц), DOCX, MD, архитектурные модели Archi валидны.

### Репозиторные инварианты и тесты
- [ ] Все тесты `backend/tests/` проходят на 100% (0 failed).
- [ ] Все 4 системных оракула возвращают PASS.
- [ ] Сборка фронтенда `npm run build` проходит с 0 ошибок TypeScript.
- [ ] Директория `docs/architecture/` строго не изменена (0 байт diff).
- [ ] 0 новых сторонних зависимостей в `requirements.txt` и `package.json`.
- [ ] Итоговый вердикт независимого аудитора: VICTORY CONFIRMED.


## 2026-09-29T08:37:02Z

# Teamwork Project Prompt — Launched

> Status: Launched  
> Goal: Craft prompt → get user approval → delegate to teamwork_preview  
> Requested team: Small, focused team

This is a single self-contained fix; keep it small and focused.

Устранение визуальных дефектов генерации PDF-отчётов в `backend/app/reports_export.py`: извлечение метрик ширин символов (`hmtx`) для формирования спецификационного массива `/W` в объекте `CIDFontType2`, балансировка весов колонок отчётов (включая 8 колонок `activity`), форматирование ISO-дат и предотвращение висячих букв и пунктуации при переносе строк.

Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm  
Integrity mode: development

## Requirements

### R1. Извлечение метрик ширин глифов (`hmtx`) и формирование массива `/W` в PDF
- В модуле `backend/app/reports_export.py`:
  * Расширить разбор TrueType шрифта `LiberationSans-Regular.ttf` (или дополнить `_build_cid_to_gid_map`):
    - Извлечь `unitsPerEm` из таблицы `head` (смещение 18, `>H`).
    - Извлечь `numberOfHMetrics` из таблицы `hhea` (смещение 34, `>H`).
    - Извлечь горизонтальные метрики из таблицы `hmtx` (`advanceWidth` для каждого GID).
  * Вычислить нормализованные ширины глифов в 1000-ных долях ем:
    $$\text{width\_1000} = \operatorname{round}\left(\frac{\text{advanceWidth} \times 1000}{\text{unitsPerEm}}\right)$$
  * Сгенерировать компактный массив `/W` для объекта `CIDFontType2` (группируя последовательные CID: `c [w1 w2 ...]`).
  * Внедрить сгенерированный массив `/W [...]` в объект `4 0 obj` перед `/DW 600`.
  * Сформировать кэш ширин символов `_CHAR_WIDTHS: dict[int, int]` для точного расчёта ширины строк при переносах.

### R2. Балансировка весов колонок таблицы (`col_weights`)
- В функции `generate_pdf_report`:
  * Задать корректные веса для всех 8 колонок отчёта `activity` (headers: `["ID события", "ID карточки", "Название", "Организация", "Из этапа", "В этап", "Исторический ответственный", "Дата перехода"]`):
    ```python
    col_weights = {
        "snapshot": [0.08, 0.22, 0.22, 0.15, 0.13, 0.10, 0.10],
        "activity": [0.07, 0.08, 0.20, 0.20, 0.13, 0.13, 0.10, 0.09],
        "created": [0.08, 0.22, 0.22, 0.15, 0.13, 0.10, 0.10],
    }
    ```
  * Обеспечить адаптивное и пропорциональное распределение ширины колонок при передаче кастомных `selected_columns`.

### R3. Точный перенос строк ячеек (`wrap_cell_text`) и форматирование дат
- В модуле `backend/app/reports_export.py`:
  * Форматирование дат: при рендеринге ячеек со значениями ISO-8601 меток времени (например, `2026-09-24T19:56:11.784833Z`) форматировать их в компактный человекочитаемый вид `24.09.2026 19:56` (или `24.09.2026\n19:56`).
  * Точный расчёт ширины текста: заменить эвристику `0.58 * font_size` на расчёт по реальным метрикам символов `_CHAR_WIDTHS`:
    $$\text{width} = \sum_{c \in \text{text}} \frac{\text{\_CHAR\_WIDTHS}[c]}{1000.0} \times \text{font\_size}$$
  * Защита от висячих букв и пунктуации: исключить перенос строки, если остаток слова составляет $\le 2$ символов (запрет строк из одиночных букв «й», «я» или одиночных знаков «:», «.»).

## Verification Resources
- Набор тестов отчётов:
  `backend/.venv/bin/pytest backend/tests/test_reports_multiformat.py -v`
  `backend/.venv/bin/pytest backend/tests/test_challenger_reports_adversarial.py -v`
  `backend/.venv/bin/pytest backend/tests/test_working_slice.py -v`
- Оракул отчётов:
  `python3 docs/checks/verify_reports.py`
- Все 4 системных оракула:
  `python3 docs/checks/verify_infra.py`
  `python3 docs/checks/verify_workflow.py`
  `python3 docs/checks/verify_reports.py`
  `python3 docs/checks/verify_plan.py`

## Acceptance Criteria

### Типографика и PDF-объекты
- [ ] Объект `CIDFontType2` в сгенерированном PDF содержит валидный массив `/W` с реальными метриками ширин глифов.
- [ ] Текст на русском языке отображается с корректными межбуквенными интервалами без наложения широких букв (`Ю`, `Ж`, `Ш`, `М`, `С`, `О`, `Д`).
- [ ] В ячейках таблицы отсутствуют строки из одиночных букв («й», «Z») и строки, начинающиеся с двоеточий или точек.
- [ ] Значения ISO-дат форматируются компактно в виде `ДД.ММ.ГГГГ ЧЧ:ММ`.

### Вёрстка таблицы
- [ ] В отчёте `activity` все 8 колонок имеют индивидуальные веса, предотвращая схлопывание в 12.5%.
- [ ] При кастомных `selected_columns` ширина колонок распределяется пропорционально сумме доступной ширины.

### Инварианты проекта
- [ ] 0 новых сторонних библиотек в `backend/requirements.txt` (чистый Python stdlib: `struct`, `io`, `zlib`, `pathlib`).
- [ ] Каталог `docs/architecture/` строго не изменён (0 байт diff).
- [ ] Все тесты `test_reports_multiformat.py`, `test_challenger_reports_adversarial.py`, `test_working_slice.py` и оракул `verify_reports.py` проходят со 100% успехом.
