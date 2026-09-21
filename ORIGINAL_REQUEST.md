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

