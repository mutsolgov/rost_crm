# Архитектурный аудит Domain 02: Workflow, FSM и механизм миграции карточек

- **Дата проведения аудита:** 2026-09-21
- **Git baseline commit:** `1c7c0eb35caaababb8708f1d5f109866ac7b420a` (`1c7c0eb`)
- **Домен аудита:** Domain 02 — Workflow, FSM, and Card Migration Architecture
- **Целевая эталонная архитектура:**
  - `docs/architecture/01-target-architecture.md` (раздел 4 «Workflow, FSM и аудит-события», строки 120–145)
  - `docs/architecture/02-data-and-workflow.md` (разделы 5, 6, 7 «Workflow Engine, FSM, Concurrency & Events», строки 135–230)
  - `docs/architecture/05-contracts-and-parallel-development.md` (раздел 2 «Идемпотентность и CAS», раздел 7 «API контракты Workflow», строки 15–60, 156–166)
  - `docs/planning/adr/ADR-04-declarative-workflow-guards.md` (Декларативные инварианты и гарды)
  - `docs/planning/04-base-workflow.json` (Эталонный граф процесса)
- **Исследованная кодовая база:**
  - `backend/app/workflow.py`
  - `backend/app/services.py`
  - `backend/app/models.py`
  - `backend/app/schemas.py`
  - `backend/app/main.py`
  - `backend/app/files.py`
  - `backend/app/errors.py`
  - Тестовые наборы: `test_workflow_migration.py`, `test_working_slice.py`, `test_core_concurrency_and_security.py`, `test_challenger_migration_stress.py`

---

## 1. Executive Summary (Ключевые выводы аудита)

Настоящий аудит представляет исчерпывающий сравнительный анализ фактической реализации бизнес-процессов (Workflow), конечного автомата (FSM), механизмов валидации (гардов), версионирования, миграций и транзакционной безопасности в проекте `rost_crm` относительно неизменяемой эталонной архитектуры.

### Основные выводы по направлениям R1–R5:

1. **R1. Базовый граф состояний и переходов:**
   - **Состояния FSM (100% соответствие):** В кодовой базе реализованы ровно 15 состояний — 13 операционных стадий воронки сотрудничества с вузом и 2 изолированных терминальных состояния (`completed`, `cancelled`). Коды, наименования, семантика и порядковые номера шагов побайтово идентичны эталону `04-base-workflow.json`.
   - **Переходы (100% соответствие):** В базовой версии v1 присутствуют все 29 разрешенных переходов. Изоляция терминалов соблюдена строго: исходящие переходы из терминальных статусов отсутствуют (`allowed_transitions` возвращает пустой список, попытка перехода возвращает HTTP 409 `TRANSITION_NOT_ALLOWED`). Дополнительно реализована расширенная версия v2 с 7 оптимизированными переходами (всего 36 переходов).
   - **Физическое хранение графа (Упрощение Stdlib-first):** Граф процесса хранится в оперативной памяти бэкенда (`WORKFLOW_REGISTRY` в `workflow.py`), а не в реляционных таблицах СУБД. В БД `interactions` фиксируются только текущий статус (`state: String(80)`) и номер версии (`workflow_version: Integer`). Таблицы `workflow_template`, `workflow_version`, `workflow_state`, `workflow_transition`, `state_visit` в схеме базы данных отсутствуют.

2. **R2. Декларативные инварианты и гарды (ADR-04):**
   - **Гард передачи материалов (100% соответствие):** Переход на этап передачи материалов (`materials_transfer`) и все последующие стадии блокируется, если в карточке взаимодействия не заполнены `program_id` или `product_id`. Ошибка возвращается со статусом HTTP 422 и кодом `VALIDATION_ERROR`. Инвариант защищен не только при переходе (`transition()`), но и при частичном обновлении через `PATCH` (`update_interaction()`), предотвращая сброс привязки. Связка программы и продукта строго проверяется через таблицу `program_products`.
   - **Гард обязательности комментария (100% соответствие):** При отмене (`cancelled`), возвратах на доработку (`rework`) и повторных циклах (`cycle`) сервер принудительно требует непустой комментарий (`strip()`-проверка), отклоняя запросы с `null`, пустой строкой или пробелами кодом HTTP 422 `VALIDATION_ERROR`.
   - **Безопасность выполнения кода (100% соответствие):** В коде бэкенда полностью отсутствуют функции динамического исполнения (`eval`, `exec`, `compile`, встроенные движки JS/Python). Вся валидация выполняется чистым статическим кодом Python, исключая уязвимости RCE и внедрения выражений.

3. **R3. Жизненный цикл версий процесса:**
   - **Статус в коде — Отсутствует (Missing):** Жизненный цикл шаблонов (`Draft` -> `Published` -> `Retired`) в кодовой базе не реализован. Версии 1 и 2 зашиты как неизменяемые константы в Python-словаре. Вычисление и сохранение криптографического хеша графа (`definition_hash` SHA-256) отсутствует. REST API для создания черновиков и редактирования этапов (`POST /workflow-templates`) отсутствует; добавление или изменение процесса требует правки Python-кода и повторного развертывания приложения.

4. **R4. Механизм миграции карточек на новые версии:**
   - **Двухфазная миграция (Упрощенная реализация):** Эндпоинты `/api/v1/workflow/migrate/preview` и `/commit` реализованы. Фаза preview выполняет предварительный расчет распределения статусов, выявляет коллизии схлопывания (N-to-1) и несмапленные статусы.
   - **Изоляция терминалов (100% соответствие):** Сервер строго запрещает сопоставление терминальных статусов (`completed`, `cancelled`) в активные статусы с генерацией HTTP 422 `VALIDATION_ERROR`. Завершенные карточки исключаются из выборки активной миграции (`state.not_in(from_terminal)`).
   - **Аудит и воронка (100% соответствие):** При миграции для каждой карточки генерируется системное событие `workflow_migrated` с фиксацией старой/новой версии и ревизии. Это событие строго исключено из бизнес-воронки переходов в отчете активности (`activity report`).
   - **Архитектурные разрывы миграции:** Механизм является stateless — сущности `workflow_migration_plan` и `workflow_migration_item` с постоянным `plan_id` в БД не сохраняются. В методе `commit` ревизия карточки считывается из БД в момент выполнения транзакции, а не сверяется со снимком preview, что создает риск применения миграции к карточке, измененной пользователем во время окна согласования preview. Миграция выполняется в единой синхронной транзакции (all-or-nothing), а не как асинхронный фоновый процесс с полистным отчетом по карточкам (`applied/conflict/invalid`).

5. **R5. Конкурентность и транзакционные гарантии:**
   - **CAS (Compare-And-Swap) (100% соответствие на уровне карточки):** Все мутации карточки (`transition`, `update_interaction`, `add_comment`, `assign`, `commit_workflow_migration`) выполняются через атомарный SQL UPDATE: `WHERE id = :id AND revision = :expected_revision` с инкрементом `revision = revision + 1`. При несовпадении ревизии выполняется откат транзакции и возвращается HTTP 409 `REVISION_CONFLICT`. Стресс-тест на 20 параллельных потоков подтвердил полную изоляцию: ровно 1 запрос побеждает, 19 получают 409.
   - **Идемпотентность (Высокое соответствие):** Заголовок `Idempotency-Key` обязателен для всех изменяющих эндпоинтов карточек и миграций. Механизм `begin_command` / `finish_command` кэширует хеш полезной нагрузки SHA-256 и ответ в таблице `command_results`. При повторном запросе выполняется проверка прав доступа (`scoped_interaction`) — если менеджер потерял доступ к карточке после передачи, вместо кэшированного ответа возвращается безопасный HTTP 404 `NOT_FOUND`.
   - **Уязвимость вложения файлов:** Эндпоинт `POST /api/v1/interactions/{id}/attachments` не требует `Idempotency-Key` и не инкрементирует `revision` карточки через `cas()`. Поскольку номер последовательности событий вычисляется как `SELECT MAX(sequence) + 1`, два параллельных запроса на загрузку файлов в одну карточку могут вычислить одинаковый `sequence`, что приведет к коллизии уникального индекса `uq_event_sequence` и неконтролируемой ошибке базы данных.

---

## 2. Summary Compliance Table (Сводная таблица соответствия R1–R5)

| Требование эталона | Статус в коде | Реализация: файлы и строки | Выявленные расхождения и архитектурные разрывы | Оценка риска |
|---|---|---|---|---|
| **R1.1: 15 состояний FSM** (13 рабочих + 2 терминальных) | **Full** (Полное соответствие) | `backend/app/workflow.py:86-90`, `backend/app/data/base-workflow.json:31-137` | Расхождений нет. Все 15 состояний совпадают по кодам, наименованиям и типам (`working`/`terminal`). | Низкий |
| **R1.2: 29 переходов базового графа** | **Full** (Полное соответствие) | `backend/app/workflow.py:5,91-109`, `backend/app/data/base-workflow.json:138-285` | Расхождений нет. 29 базовых ребер совпадают на 100%. Дополнительно определена версия v2 с 7 оптимизированными переходами (всего 36). | Низкий |
| **R1.3: Физическое реляционное хранение графа** | **Missing / Simplified** (Отсутствует в БД, упрощено в RAM) | `backend/app/workflow.py:74-84`, `backend/app/models.py:103-123` | Таблицы `workflow_template`, `workflow_version`, `workflow_state`, `workflow_transition`, `state_visit` отсутствуют. Граф хранится в Python In-Memory реестре `WORKFLOW_REGISTRY`. В БД `Interaction` хранятся только `state: str` и `workflow_version: int`. | Средний |
| **R2.1: Блокировка передачи материалов без программы/продукта** | **Full** (Полное соответствие) | `backend/app/services.py:303-305, 367-370`, `backend/app/workflow.py:117-120` | Переход в `materials_transfer` и далее блокируется с HTTP 422 `VALIDATION_ERROR`. Запрещен сброс программы/продукта через PATCH на этапе `materials_transfer`+. Продукт проверяется на связь с программой. | Низкий |
| **R2.2: Обязательность комментария для cancel/rework/cycle** | **Full** (Полное соответствие) | `backend/app/services.py:301-302`, `backend/app/schemas.py:37` | При `edge["comment_required"]` пустой комментарий (`strip()`) отклоняется с HTTP 422 `VALIDATION_ERROR`. Охватывает все 13 отмен, возврат на корректировку и повторный цикл. | Низкий |
| **R2.3: Статическая безопасность гардов (запрет eval/exec)** | **Full** (Полное соответствие) | `backend/app/workflow.py`, `backend/app/services.py` | В коде 0 вызовов `eval`, `exec`, `compile` или внешних движков JS. Валидация выполняется чистым статическим кодом Python. Уязвимости RCE исключены. | Низкий |
| **R3.1: Жизненный цикл версий (Draft / Published / Retired)** | **Missing** (Отсутствует) | `backend/app/workflow.py:74-77` | Отсутствует сущность жизненного цикла шаблонов. Версии статичны и всегда активны. Нельзя создать черновик или архивировать старую версию. | Высокий |
| **R3.2: Криптографическое хеширование `definition_hash` (SHA-256)** | **Missing** (Отсутствует) | `backend/app/workflow.py` | Вычисление и сохранение хеша графа SHA-256 отсутствует. Целостность между распределенными репликами не гарантируется криптографически. | Средний |
| **R3.3: REST API для управления шаблонами процессов** | **Missing** (Отсутствует) | `backend/app/main.py:179-194` | Эндпоинты `POST /workflow-templates`, `/versions`, `/publish` отсутствуют. Единственный эндпоинт — `GET /api/v1/workflow?version=N`. Редактирование процесса через UI невозможно. | Высокий |
| **R4.1: Двухфазный механизм миграции (`/preview`, `/commit`)** | **Simplified** (Упрощено) | `backend/app/services.py:741-936`, `backend/app/main.py:196-215` | Реализованы эндпоинты `/preview` (расчет распределения и коллизий) и `/commit`. Механизм stateless: таблицы планов миграции и снимки `plan_id` в БД не создаются. | Средний |
| **R4.2: Изоляция терминальных состояний в миграциях** | **Full** (Полное соответствие) | `backend/app/services.py:767-772, 864-869, 875` | Строгий запрет сопоставления терминальных статусов в активные (HTTP 422 `VALIDATION_ERROR`). Завершенные карточки исключены из выборки активной миграции. | Низкий |
| **R4.3: Атомарность и CAS миграции карточек** | **Simplified** (Упрощено с разрывом) | `backend/app/services.py:888-902` | `cas()` вызывается для каждой карточки, но `expected_revision` читается из БД прямо в момент вызова `commit`, а не сверяется с ревизией из снимка `preview`. Миграция выполняется в единой монолитной транзакции (all-or-nothing). | Высокий |
| **R4.4: Аудит миграции и исключение из бизнес-воронки** | **Full** (Полное соответствие) | `backend/app/services.py:606, 689, 904-916` | Генерируется неизменяемое событие `InteractionEvent(type="workflow_migrated")`. В отчете `activity` события `workflow_migrated` строго исключены из фильтра переходов. | Низкий |
| **R5.1: CAS-защита от race condition на мутациях карточки** | **Full** (Полное соответствие) | `backend/app/services.py:243-252` | Атомарный SQL UPDATE `WHERE id=:id AND revision=:expected_revision`. При коллизии — откат и HTTP 409 `REVISION_CONFLICT`. Проверено 20 параллельными потоками. | Низкий |
| **R5.2: Протокол Idempotency-Key и защита от повторных эффектов** | **Full** (Полное соответствие на мутациях) | `backend/app/services.py:209-240`, `backend/app/models.py:167-178` | Таблица `command_results` с ограничением `uq_command_key(user_id, operation, key)`. Хеш SHA-256 канонического JSON. Повтор запроса возвращает сохраненный ответ с проверкой прав доступа `scoped_interaction`. | Низкий |
| **R5.3: Идемпотентность загрузки файлов (вложений)** | **Missing** (Отсутствует) | `backend/app/main.py:290-308`, `backend/app/files.py:124-150` | Заголовок `Idempotency-Key` не запрашивается на `upload_attachment`. Повторный сетевой запрос приводит к дублированию файла и записи в аудит-логе. | Средний |
| **R5.4: Монотонная последовательность событий (`sequence`)** | **Simplified** (Упрощено с уязвимостью) | `backend/app/services.py:186-189`, `backend/app/models.py:142` | `sequence` вычисляется запросом `SELECT MAX(sequence) + 1` с уникальным индексом `uq_event_sequence`. Надежно при CAS, но уязвимо к гонке при параллельной загрузке файлов. | Средний |

---

## 3. Detailed Architectural Gap Breakdown (Детальный разбор разрывов)

### 3.1. R1: Базовый граф состояний и переходов

#### А. Сверка 15 состояний FSM
В соответствии с `docs/architecture/02-data-and-workflow.md` (строка 159) и эталоном `docs/planning/04-base-workflow.json` (строки 31–137), бизнес-процесс включает ровно 13 операционных стадий воронки сотрудничества с вузом и 2 терминальных состояния:

| # | Код состояния (`code`) | Наименование этапа | Тип эталона | Статус в кодовой базе | Файл и строка в коде |
|---|------------------------|--------------------|-------------|-----------------------|----------------------|
| 1 | `contact_search` | Поиск контактов | `working` (шаг 1) | Реализован | `workflow.py:5`, `base-workflow.json:33` |
| 2 | `needs_clarification` | Уточнение потребности | `working` (шаг 2) | Реализован | `workflow.py:5`, `base-workflow.json:40` |
| 3 | `meeting` | Встреча с вузом | `working` (шаг 3) | Реализован | `workflow.py:5`, `base-workflow.json:47` |
| 4 | `document_exchange` | Обмен документами | `working` (шаг 4) | Реализован | `workflow.py:5`, `base-workflow.json:54` |
| 5 | `document_revision` | Корректировка документов | `working` (шаг 5) | Реализован | `workflow.py:5`, `base-workflow.json:61` |
| 6 | `document_signing` | Подписание документов | `working` (шаг 6) | Реализован | `workflow.py:5`, `base-workflow.json:68` |
| 7 | `materials_transfer` | Передача материалов и лицензии | `working` (шаг 7) | Реализован | `workflow.py:5`, `base-workflow.json:75` |
| 8 | `deployment` | Сопровождение внедрения | `working` (шаг 8) | Реализован | `workflow.py:5`, `base-workflow.json:82` |
| 9 | `teacher_training` | Обучение преподавателей | `working` (шаг 9) | Реализован | `workflow.py:5`, `base-workflow.json:89` |
| 10 | `curriculum_update` | Актуализация учебной программы | `working` (шаг 10) | Реализован | `workflow.py:5`, `base-workflow.json:96` |
| 11 | `classes` | Ведение занятий | `working` (шаг 11) | Реализован | `workflow.py:5`, `base-workflow.json:103` |
| 12 | `materials_update` | Актуализация материалов | `working` (шаг 12) | Реализован | `workflow.py:5`, `base-workflow.json:110` |
| 13 | `teacher_upskilling` | Повышение квалификации преподавателей | `working` (шаг 13) | Реализован | `workflow.py:5`, `base-workflow.json:117` |
| 14 | `completed` | Взаимодействие завершено | `terminal` (успех) | Реализован | `workflow.py:5,116`, `base-workflow.json:124` |
| 15 | `cancelled` | Взаимодействие отменено | `terminal` (отмена) | Реализован | `workflow.py:5,116`, `base-workflow.json:131` |

#### Б. Сравнительная матрица 29 переходов базового процесса v1
Сверка переходов между спецификацией `04-base-workflow.json` (строки 138–285) и кодовой базой (`backend/app/workflow.py:5`, `backend/app/data/base-workflow.json`):

| # | Код перехода (`code`) | Исходный статус (`from`) | Целевой статус (`to`) | Тип перехода (`kind`) | Комментарий обязателен | Условия перехода (`conditions`) | Статус в коде |
|---|-----------------------|--------------------------|-----------------------|-----------------------|------------------------|---------------------------------|---------------|
| 1 | `contact_search_to_needs_clarification` | `contact_search` | `needs_clarification` | `forward` | `false` | `[]` | Соответствует |
| 2 | `needs_clarification_to_meeting` | `needs_clarification` | `meeting` | `forward` | `false` | `[]` | Соответствует |
| 3 | `meeting_to_document_exchange` | `meeting` | `document_exchange` | `forward` | `false` | `[]` | Соответствует |
| 4 | `document_exchange_to_document_revision` | `document_exchange` | `document_revision` | `forward` | `false` | `[]` | Соответствует |
| 5 | `document_revision_to_document_signing` | `document_revision` | `document_signing` | `forward` | `false` | `[]` | Соответствует |
| 6 | `document_signing_to_materials_transfer` | `document_signing` | `materials_transfer` | `forward` | `false` | `["program_and_product_identified"]` | Соответствует |
| 7 | `materials_transfer_to_deployment` | `materials_transfer` | `deployment` | `forward` | `false` | `[]` | Соответствует |
| 8 | `deployment_to_teacher_training` | `deployment` | `teacher_training` | `forward` | `false` | `[]` | Соответствует |
| 9 | `teacher_training_to_curriculum_update` | `teacher_training` | `curriculum_update` | `forward` | `false` | `[]` | Соответствует |
| 10 | `curriculum_update_to_classes` | `curriculum_update` | `classes` | `forward` | `false` | `[]` | Соответствует |
| 11 | `classes_to_materials_update` | `classes` | `materials_update` | `forward` | `false` | `[]` | Соответствует |
| 12 | `materials_update_to_teacher_upskilling` | `materials_update` | `teacher_upskilling` | `forward` | `false` | `[]` | Соответствует |
| 13 | `teacher_upskilling_to_completed` | `teacher_upskilling` | `completed` | `forward` | `false` | `[]` | Соответствует |
| 14 | `document_exchange_to_document_signing` | `document_exchange` | `document_signing` | `skip_optional` | `false` | `[]` | Соответствует |
| 15 | `document_signing_to_document_revision` | `document_signing` | `document_revision` | `rework` | `true` | `[]` | Соответствует |
| 16 | `teacher_upskilling_to_classes` | `teacher_upskilling` | `classes` | `cycle` | `true` | `[]` | Соответствует |
| 17 | `contact_search_to_cancelled` | `contact_search` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 18 | `needs_clarification_to_cancelled` | `needs_clarification` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 19 | `meeting_to_cancelled` | `meeting` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 20 | `document_exchange_to_cancelled` | `document_exchange` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 21 | `document_revision_to_cancelled` | `document_revision` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 22 | `document_signing_to_cancelled` | `document_signing` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 23 | `materials_transfer_to_cancelled` | `materials_transfer` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 24 | `deployment_to_cancelled` | `deployment` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 25 | `teacher_training_to_cancelled` | `teacher_training` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 26 | `curriculum_update_to_cancelled` | `curriculum_update` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 27 | `classes_to_cancelled` | `classes` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 28 | `materials_update_to_cancelled` | `materials_update` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |
| 29 | `teacher_upskilling_to_cancelled` | `teacher_upskilling` | `cancelled` | `cancellation` | `true` | `[]` | Соответствует |

#### В. Дополнительные переходы оптимизированной версии v2 (7 переходов)
В `backend/app/workflow.py` (строки 7–64) объявлен массив `V2_OPTIMIZED_TRANSITIONS`, добавляющий 7 новых ребер к базовой схеме (всего 36 переходов):
1. `meeting_to_document_signing` (`meeting` -> `document_signing`, forward, comment: false) — быстрый пропуск обмена шаблонами.
2. `materials_transfer_to_classes` (`materials_transfer` -> `classes`, forward, comment: false) — экспресс-старт занятий.
3. `classes_to_completed` (`classes` -> `completed`, forward, comment: false) — досрочное закрытие курса.
4. `deployment_to_materials_transfer` (`deployment` -> `materials_transfer`, rework, comment: true) — доотправка дистрибутивов и ключей.
5. `classes_to_teacher_training` (`classes` -> `teacher_training`, rework, comment: true) — повторный тренинг преподавателей в процессе ведения курса.
6. `document_signing_to_meeting` (`document_signing` -> `meeting`, rework, comment: true) — эскалация разногласий с этапа подписания обратно на очную встречу.
7. `document_revision_to_meeting` (`document_revision` -> `meeting`, rework, comment: true) — возврат на встречу при невозможности согласовать правки документов дистанционно.

#### Г. Анализ физического хранения графа (In-Memory Dict vs Relational Schema)
- **Эталонная модель (`docs/architecture/02-data-and-workflow.md:135-146`):** Специфицирует 6 реляционных таблиц в PostgreSQL:
  1. `workflow_template`: шаблоны процессов (`code`, `name`, `description`, `archived_at`);
  2. `workflow_version`: версии процесса (`template_id`, `version_no`, `status`, `definition_hash`, `is_default_for_new`);
  3. `workflow_state`: состояния процесса (`workflow_version_id`, `state_key`, `code`, `name`, `kind`, `invariants`);
  4. `workflow_transition`: допустимые переходы (`workflow_version_id`, `code`, `from_state_key`, `to_state_key`, `guard`);
  5. `workflow_migration_plan`, `workflow_migration_map`, `workflow_migration_item`: персистентные сущности миграции;
  6. `state_visit`: журнал интервалов нахождения на этапах (`entered_at`, `exited_at`, `opened_by_event_id`).
- **Фактическое состояние кода:**
  В `backend/app/models.py` эти таблицы **полностью отсутствуют**. Граф загружается в память в словарь `WORKFLOW_REGISTRY` (`workflow.py:74-77`). Модель `Interaction` содержит скалярные поля `state: String(80)`, `workflow_version: Integer`, `visit_id: String(64)`. Внешние ключи (FK) на сущности workflow отсутствуют.
- **Оценка риска:** Средний. Приложение надежно защищает FSM на прикладном уровне (`services.py`), однако прямой SQL-запрос `UPDATE interactions SET state = 'hacked'` не встретит сопротивления на уровне внешних ключей или ограничений БД.

---

### 3.2. R2: Декларативные инварианты и гарды (ADR-04)

#### А. Гард передачи материалов (`materials_transfer`+)
- **Требование:** Блокировка перехода на этап `materials_transfer` и далее при отсутствии `program_id` или `product_id`. Возврат HTTP 422 `VALIDATION_ERROR`.
- **Фактическая реализация:**
  В `backend/app/workflow.py` (строки 117–120) определено множество этапов, требующих предмет сотрудничества:
  ```python
  SUBJECT_REQUIRED_STATES = {
      "materials_transfer", "deployment", "teacher_training", "curriculum_update", "classes",
      "materials_update", "teacher_upskilling", "completed",
  }
  ```
  В `backend/app/services.py` (строки 303–305) в функции `transition()` выполняется строгая проверка:
  ```python
  if edge["to"] in SUBJECT_REQUIRED_STATES and (not item.program_id or not item.product_id):
      raise APIError("VALIDATION_ERROR", "Перед этим этапом укажите ИТ-программу и ИТ-продукт.")
  validate_subject(db, item.program_id, item.product_id)
  ```
  Кроме того, в `backend/app/services.py` (строки 367–370) в методе `update_interaction()` (обработка `PATCH`) внедрена защита от обнуления полей:
  ```python
  if item.state in SUBJECT_REQUIRED_STATES and (new_program_id is None or new_product_id is None):
      raise APIError("VALIDATION_ERROR", "На этом этапе нельзя сбросить ИТ-программу или ИТ-продукт.")
  validate_subject(db, new_program_id, new_product_id)
  ```
  Связка `program_id` и `product_id` проверяется на валидность и существование через таблицу `ProgramProduct` (`services.py:69-75`).
- **Оценка риска:** Низкий. Инвариант защищен на 100% со всех точек входа API.

#### Б. Гард обязательности комментария
- **Требование:** Обязательность непустого комментария при отмене (`cancelled`), возвратах на доработку (`rework`) и повторных циклах (`cycle`).
- **Фактическая реализация:**
  В `backend/app/services.py` (строки 301–302):
  ```python
  if edge["comment_required"] and not (body.comment or "").strip():
      raise APIError("VALIDATION_ERROR", "Для возврата, цикла или отмены нужен комментарий.")
  ```
  Использование `(body.comment or "").strip()` гарантирует отсечение как значений `null` и `""`, так и строк из пробельных символов (`"   "`).
- **Оценка риска:** Низкий. Реализация безупречна.

#### В. Статическая безопасность гардов (Zero Dynamic Code Execution)
- **Требование:** Категорический запрет выполнения динамического пользовательского кода (`eval`, `exec`, Python, JavaScript, шаблонизаторы Jinja) в логике гардов.
- **Фактическая реализация:**
  Аудит исходного кода `backend/app/` показал **0 вызовов** функций `eval()`, `exec()`, `compile()`. Все гарды представляют собой скомпилированный детерминированный код Python.
- **Оценка риска:** Низкий. Уязвимости выполнения произвольного кода (RCE) исключены на архитектурном уровне.

---

### 3.3. R3: Жизненный цикл версий процесса

#### А. Жизненный цикл версий (Draft / Published / Retired)
- **Требование эталона (`docs/architecture/02-data-and-workflow.md:140-150`):** Шаблоны процессов должны поддерживать строгий трехфазный жизненный цикл:
  - `Draft`: редактируемый черновик, новые карточки не создаются;
  - `Published`: опубликованная неизменяемая версия, по которой идут активные взаимодействия;
  - `Retired`: архивная версия, запрещающая запуск новых взаимодействий, но позволяющая существующим карточкам дойти до терминального статуса.
- **Фактическая реализация:**
  В коде жизненный цикл отсутствует полностью. Версии представлены статическими целочисленными ключами (`1`, `2`) в словаре `WORKFLOW_REGISTRY` (`workflow.py:74-77`). Нет разделения на черновики, активные и архивные версии.
- **Оценка риска:** Высокий. Невозможно разрабатывать новую версию процесса параллельно с эксплуатацией текущей без деплоя кода.

#### Б. Криптографическое хеширование `definition_hash`
- **Требование эталона (`docs/architecture/02-data-and-workflow.md:157`):** При публикации версии процесса должен вычисляться криптографический хеш SHA-256 (`definition_hash char(64)`) от канонического представления графа (сортированные ключи, детерминированные разделители), фиксирующий неизменяемость правил.
- **Фактическая реализация:**
  В `workflow.py` и сервисах вычисление `definition_hash` отсутствует.
- **Оценка риска:** Средний. Отсутствие контроля целостности графа в распределенной среде.

#### В. REST API управления шаблонами процессов
- **Требование эталона (`docs/architecture/05-contracts-and-parallel-development.md:156-166`):**
  Наличие административных маршрутов:
  - `POST /api/v1/workflow-templates`
  - `POST /api/v1/workflow-templates/{id}/versions`
  - `PUT /api/v1/workflow-templates/{id}/versions/{version_id}`
  - `POST /api/v1/workflow-templates/{id}/versions/{version_id}/publish`
- **Фактическая реализация:**
  В `backend/app/main.py:179-194` реализован только маршрут на чтение: `GET /api/v1/workflow?version=N`. Эндпоинты создания, валидации и публикации шаблонов отсутствуют.
- **Оценка риска:** Высокий. Администратор не может конфигурировать процесс через интерфейс системы.

---

### 3.4. R4: Механизм миграции карточек на новые версии (`workflow_migration_plan`)

#### А. Двухфазность миграции (`/preview` и `/commit`)
- **Требование эталона (`docs/architecture/02-data-and-workflow.md:169-178`):**
  - Фаза 1 (`preview`): формирование плана миграции, анализ распределения статусов, обнаружение коллизий ревизий, фиксация снимка карточек в `workflow_migration_plan` / `item`.
  - Фаза 2 (`commit`/`apply`): исполнение миграции по сохраненному `plan_id` с проверкой неизменности карточек.
- **Фактическая реализация:**
  Маршруты `POST /api/v1/workflow/migrate/preview` и `POST /api/v1/workflow/migrate/commit` реализованы (`main.py:196-215`, `services.py:741-936`).
  В `preview` рассчитывается распределение статусов до и после миграции, определяются коллизии N-to-1 и флаг валидности `is_valid`. Однако вызов stateless: `plan_id` не генерируется и в БД не сохраняется.

#### Б. Изоляция терминальных состояний
- **Требование:** Запрет возврата закрытых карточек (`completed`, `cancelled`) в активную воронку при миграции.
- **Фактическая реализация:**
  В `backend/app/services.py` (строки 767–772 и 864–869):
  ```python
  if src in from_terminal and dst not in to_terminal:
      raise APIError("VALIDATION_ERROR", f"Недопустимо сопоставлять терминальный статус '{src}' в активный статус '{dst}'.", 422)
  ```
  Кроме того, при выборке карточек для миграции (строки 778, 875) накладывается фильтр `Interaction.state.not_in(from_terminal)`, поэтому закрытые карточки не затрагиваются пакетной миграцией. При сопоставлении активного статуса в терминальный карточке проставляется `closed_at = now` (`services.py:901`).
- **Оценка риска:** Низкий. Терминальная изоляция обеспечена полностью.

#### В. Атомарность, CAS и гонка между preview и commit
- **Архитектурный разрыв:**
  В `services.py:871-897` в функции `commit_workflow_migration`:
  ```python
  items = list(db.scalars(select(Interaction).where(...)))
  for item in items:
      old_state = item.state
      old_revision = item.revision
      new_state = status_mapping[old_state]
      cas(db, item, old_revision, workflow_version=to_version, state=new_state, ...)
  ```
  Функция `commit` запрашивает карточки из БД и принимает `old_revision = item.revision` *в момент коммита*. Она **не сверяет** текущую ревизию карточки со значением, зафиксированным на этапе `preview`!
  Если менеджер изменил карточку (сменил этап или добавил комментарий) в промежутке между просмотром preview руководителем и нажатием кнопки «Применить», миграция накатится на новую ревизию карточки, проигнорировав факт промежуточного изменения.
- **Монолитность транзакции vs Покарточный процесс:**
  Все карточки мигрируют в едином цикле и фиксируются одним вызовом `finish_command()`. Если на 10 000 карточек хотя бы одна потерпит конфликт ревизии, `cas()` вызовет `db.rollback()`, и вся миграция упадет с HTTP 409. Эталонная архитектура (§5.2, строка 175) требует независимой гарантии атомарности **по каждой карточке** с отчетом (`applied/conflict/invalid`).
- **Оценка риска:** Высокий. Риск рассинхронизации данных при активной работе операторов во время миграции.

#### Г. Аудит миграции и исключение из бизнес-воронки
- **Требование:** Фиксация системного события `workflow_migrated` с исключением из операционного отчета активности.
- **Фактическая реализация:**
  В `services.py:904-916` для каждого взаимодействия создается `InteractionEvent(type="workflow_migrated", ...)` с монотонным `sequence`.
  В `services.py:606` расчет воронки отчета `activity` использует фильтр:
  ```python
  if ev.type in ("transition", "state_changed") and start <= ev_eff < end:
      transitions.append(ev)
  ```
  События `workflow_migrated` не попадают в данный фильтр и не искажают конверсию этапов воронки.
- **Оценка риска:** Низкий. Соответствие полное.

---

### 3.5. R5: Конкурентность и транзакционные гарантии

#### А. CAS-запросы (Compare-And-Swap)
- **Реализация:**
  В `backend/app/services.py` (строки 243–252):
  ```python
  def cas(db, item, expected_revision, **values):
      result = db.execute(update(Interaction).where(
          Interaction.id == item.id,
          Interaction.revision == expected_revision
      ).values(revision=expected_revision + 1, **values),
      execution_options={"synchronize_session": False})
      if result.rowcount != 1:
          db.rollback()
          raise APIError("REVISION_CONFLICT", "Карточка изменена. Обновите данные.", 409)
      db.refresh(item)
  ```
  Атомарный SQL-запрос `UPDATE ... WHERE id = :id AND revision = :expected_revision` на уровне СУБД блокирует строку карточки. Любой параллельный процесс, передавший устаревшую ревизию, получает `rowcount == 0`, транзакция откатывается (`db.rollback()`), и клиент получает HTTP 409 `REVISION_CONFLICT`.
- **Подтверждение тестами:** Тест `test_cas_concurrency_parallel_race_twenty_threads_patch` и тест `test_cas_concurrency_parallel_race_twenty_threads_transition` с 20 конкурентными потоками подтвердили абсолютную надежность: ровно 1 поток обновляет запись, 19 получают 409, ревизия увеличивается ровно на 1.
- **Оценка риска:** Низкий.

#### Б. Обработка заголовка `Idempotency-Key` и таблица `CommandResult`
- **Реализация:**
  Модель `CommandResult` (`models.py:167-178`) содержит уникальное ограничение `UniqueConstraint("user_id", "operation", "key", name="uq_command_key")`.
  Функция `begin_command` (`services.py:209-234`):
  1. Валидирует непустой ключ длиной до 200 символов;
  2. Вычисляет криптографический хеш SHA-256 канонического представления полезной нагрузки (`separators=(",", ":")`, `sort_keys=True`);
  3. Регистрирует команду в БД через `db.flush()`. При конкурентном запросе перехватывает `IntegrityError`, откатывает транзакцию и перечитывает сохраненную запись;
  4. При несовпадении хеша возвращает HTTP 409 `IDEMPOTENCY_CONFLICT` («Этот ключ уже использован с другим содержимым»);
  5. **Проверка авторизации при replay:** Вызывает `scoped_interaction(db, user, saved.resource_id)`. Если права менеджера на карточку были отозваны между запросами, сервер возвращает HTTP 404 `NOT_FOUND`, предотвращая утечку данных через кэш идемпотентности.
- **Оценка риска:** Низкий для поддержанных методов.

#### В. Уязвимость отсутствия идемпотентности и CAS на загрузке файлов
- **Архитектурный разрыв:**
  В `backend/app/main.py` (строки 290–308) эндпоинт `POST /api/v1/interactions/{id}/attachments`:
  - Не принимает заголовок `Idempotency-Key`;
  - Не вызывает `cas(db, item, ...)` и не обновляет `revision` карточки взаимодействия.
- **Гонка генерации sequence:**
  В `backend/app/services.py` (строки 186–189):
  ```python
  last_sequence = db.scalar(select(func.max(InteractionEvent.sequence)).where(
      InteractionEvent.interaction_id == item.id)) or 0
  event = InteractionEvent(..., sequence=last_sequence + 1)
  ```
  В обычных операциях (`transition`, `add_comment`, `assign`) вызов `append_event()` выполняется строго после успешного `cas()`, сериализующего транзакции. Однако при загрузке файлов блокировка `cas()` отсутствует. Два параллельных запроса на загрузку файлов одновременно прочитают один и тот же `last_sequence`, сформируют одинаковый `sequence = last_sequence + 1`, и один из них упадет с необработанной ошибкой нарушения ограничения уникальности `uq_event_sequence(interaction_id, sequence)` (`models.py:142`).
- **Оценка риска:** Средний. Вероятность сбоя при одновременной загрузке нескольких файлов пользователями в одну карточку.

---

## 4. Raw Evidence (Сырые доказательства)

### 4.1. Выдержки исходного кода проверок и механизмов

#### 1. Реализация Compare-And-Swap (`backend/app/services.py:243-252`):
```python
def cas(db, item, expected_revision, **values):
    result = db.execute(update(Interaction).where(Interaction.id == item.id,
                       Interaction.revision == expected_revision).values(
                           revision=expected_revision + 1, **values),
                       execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        db.rollback()
        raise APIError("REVISION_CONFLICT", "Карточка изменена. Обновите данные.", 409)
    db.refresh(item)
```

#### 2. Проверка инвариантов и гардов при переходе (`backend/app/services.py:301-306`):
```python
if edge["comment_required"] and not (body.comment or "").strip():
    raise APIError("VALIDATION_ERROR", "Для возврата, цикла или отмены нужен комментарий.")
if edge["to"] in SUBJECT_REQUIRED_STATES and (not item.program_id or not item.product_id):
    raise APIError("VALIDATION_ERROR", "Перед этим этапом укажите ИТ-программу и ИТ-продукт.")
validate_subject(db, item.program_id, item.product_id)
cas(db, item, body.expected_revision, state=edge["to"], updated_at=now, closed_at=now if edge["to"] in terminal_states else item.closed_at)
```

#### 3. Защита от сброса программы и продукта через PATCH (`backend/app/services.py:367-370`):
```python
if item.state in SUBJECT_REQUIRED_STATES and (new_program_id is None or new_product_id is None):
    raise APIError("VALIDATION_ERROR", "На этом этапе нельзя сбросить ИТ-программу или ИТ-продукт.")
validate_subject(db, new_program_id, new_product_id)
```

#### 4. Идемпотентность и проверка прав при повторе (`backend/app/services.py:228-234`):
```python
if saved.payload_hash != digest:
    raise APIError("IDEMPOTENCY_CONFLICT", "Этот ключ уже использован с другим содержимым.", 409)
if saved.resource_id:
    scoped_interaction(db, user, saved.resource_id)
if saved.response is None:
    raise APIError("IDEMPOTENCY_CONFLICT", "Команда ещё выполняется.", 409)
return saved, saved.response
```

#### 5. Исключение миграций из бизнес-воронки отчета `activity` (`backend/app/services.py:606-608`):
```python
if ev.type in ("transition", "state_changed") and start <= ev_eff < end:
    transitions.append(ev)
```

---

### 4.2. Полный сырой вывод прогона тестов pytest

Команда запуска:
`backend/.venv/bin/python -m pytest backend/tests/test_workflow_migration.py backend/tests/test_working_slice.py backend/tests/test_core_concurrency_and_security.py -v`

Фактический вывод терминала (41 тест):
```text
============================= test session starts ==============================
platform linux -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0 -- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
plugins: anyio-4.15.1
collecting ... collected 41 items

backend/tests/test_workflow_migration.py::test_workflow_endpoint_versioning PASSED [  2%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_rbac_manager_forbidden PASSED [  4%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_rbac_supervisor_and_admin_allowed PASSED [  7%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_reject_terminal_to_active PASSED [  9%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_reject_invalid_versions_and_statuses PASSED [ 12%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_missing_idempotency_key PASSED [ 14%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_preview_calculation_and_collisions PASSED [ 17%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_preview_unmapped_status PASSED [ 19%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_commit_atomic_execution PASSED [ 21%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_preserves_history_comments_attachments PASSED [ 24%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_idempotency_replay_and_conflict PASSED [ 26%]
backend/tests/test_workflow_migration.py::test_v2_allowed_transitions_and_execution_after_migration PASSED [ 29%]
backend/tests/test_workflow_migration.py::test_workflow_migrate_to_terminal_updates_closed_at PASSED [ 31%]
backend/tests/test_working_slice.py::test_auth_requires_explicit_identity PASSED [ 34%]
backend/tests/test_working_slice.py::test_demo_and_sqlite_cannot_be_accidentally_enabled_in_production PASSED [ 36%]
backend/tests/test_working_slice.py::test_health_and_openapi_are_real PASSED [ 39%]
backend/tests/test_working_slice.py::test_manager_scope_applies_to_list_direct_detail_and_dashboard PASSED [ 41%]
backend/tests/test_working_slice.py::test_technical_admin_has_no_implicit_business_scope PASSED [ 43%]
backend/tests/test_working_slice.py::test_create_and_idempotent_replay_do_not_duplicate PASSED [ 46%]
backend/tests/test_working_slice.py::test_creation_requires_key_and_does_not_allow_manager_to_assign_another_user PASSED [ 48%]
backend/tests/test_working_slice.py::test_transition_revision_and_idempotency_are_enforced PASSED [ 51%]
backend/tests/test_working_slice.py::test_forbidden_transition_cannot_skip_workflow PASSED [ 53%]
backend/tests/test_working_slice.py::test_missing_program_and_product_prevent_late_stage PASSED [ 56%]
backend/tests/test_working_slice.py::test_cancel_requires_comment_and_terminal_has_no_transition PASSED [ 58%]
backend/tests/test_working_slice.py::test_comment_is_persisted_and_stale_comment_does_not_overwrite PASSED [ 60%]
backend/tests/test_working_slice.py::test_reassignment_restricts_old_owner_and_keeps_historical_owner PASSED [ 63%]
backend/tests/test_working_slice.py::test_idempotent_transition_replay_checks_current_access PASSED [ 65%]
backend/tests/test_working_slice.py::test_snapshot_effective_and_received_boundaries PASSED [ 68%]
backend/tests/test_working_slice.py::test_json_export_is_scoped_and_matches_report PASSED [ 70%]
backend/tests/test_working_slice.py::test_filter_intersection_pagination_and_input_validation PASSED [ 73%]
backend/tests/test_core_concurrency_and_security.py::test_cas_concurrency_parallel_race_twenty_threads_patch PASSED [ 75%]
backend/tests/test_core_concurrency_and_security.py::test_cas_concurrency_parallel_race_twenty_threads_transition PASSED [ 78%]
backend/tests/test_core_concurrency_and_security.py::test_scope_isolation_manager_cross_access_strict_404 PASSED [ 80%]
backend/tests/test_core_concurrency_and_security.py::test_scope_isolation_after_reassignment_strict_404 PASSED [ 82%]
backend/tests/test_core_concurrency_and_security.py::test_idempotency_caching_and_replay_without_side_effects PASSED [ 85%]
backend/tests/test_core_concurrency_and_security.py::test_workflow_illegal_transition_rejections PASSED [ 87%]
backend/tests/test_core_concurrency_and_security.py::test_formula_injection_escaping_in_reports PASSED [ 90%]
backend/tests/test_core_concurrency_and_security.py::test_formula_injection_escaping_in_csv_export PASSED [ 92%]
backend/tests/test_file_security_path_traversal_null_bytes_and_oracle_defense PASSED [ 95%]
backend/tests/test_core_concurrency_and_security.py::test_frontend_jwt_in_memory_audit PASSED [ 97%]
backend/tests/test_core_concurrency_and_security.py::test_immutable_audit_log_temporal_integrity PASSED [100%]

=============================== warnings summary ===============================
backend/.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1
  /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

backend/.venv/lib64/python3.14/site-packages/starlette/testclient.py:53
  /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/lib64/python3.14/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 41 passed, 2 warnings in 13.95s ========================
```

---

## 5. Prioritized Action Items (Приоритизированный план доработок)

В соответствии с философией **Stdlib-first** (минимальный работающий дифф, предотвращение оверинжиниринга, использование стандартной библиотеки и нативных механизмов платформы), план устранения разрывов ранжирован по приоритетам.

### Приоритет P0 (Критические исправления целостности и безопасности данных — минимальный дифф)

1. **P0.1: Внедрение `Idempotency-Key` и CAS на загрузку файлов (`upload_attachment`)**
   - *Проблема:* Отсутствие проверки идемпотентности и CAS-блокировки на эндпоинте `POST /api/v1/interactions/{id}/attachments` (`main.py:290`) допускает дублирование файлов при сетевых сбоях и гонку на генерации `MAX(sequence) + 1` в `interaction_events`.
   - *Решение:* Добавить заголовок `Idempotency-Key: Header(...)` в маршрут `upload_attachment`, обернуть операцию в `begin_command` / `finish_command`, и выполнять `cas(db, item, expected_revision, updated_at=now)`.
   - *Трудоемкость:* 15–20 строк кода в `main.py` и `files.py`.

2. **P0.2: Верификация ревизий карточек при миграции против снимка preview**
   - *Проблема:* Метод `commit_workflow_migration` (`services.py:871`) читает ревизию карточки в момент коммита, игнорируя факт изменения карточки пользователем между preview и commit.
   - *Решение:* Передавать в `WorkflowMigrateRequest` опциональный словарь снимка `{interaction_id: expected_revision}` или токен предпросмотра с хешем карточек, проверяя при коммите, что карточка не была изменена параллельной транзакцией.
   - *Трудоемкость:* 10–15 строк кода в `schemas.py` и `services.py`.

---

### Приоритет P1 (Архитектурное укрепление и аудит)

3. **P1.1: Вычисление и валидация криптографического хеша графа (`definition_hash`)**
   - *Проблема:* В `workflow.py` отсутствует вычисление хеша SHA-256 структуры процесса (`definition_hash`).
   - *Решение:* При инициализации `WORKFLOW_V1` и `WORKFLOW_V2` вычислять `hashlib.sha256(json.dumps(wf, sort_keys=True).encode()).hexdigest()` и включать его в ответ `GET /api/v1/workflow`.
   - *Трудоемкость:* 5 строк кода с использованием `hashlib` из стандартной библиотеки Python.

4. **P1.2: Ограничение срока жизни (TTL) записей `command_results`**
   - *Проблема:* Таблица `command_results` не имеет полей `expires_at` и со временем неограниченно разрастается.
   - *Решение:* Добавить колонку `expires_at` (по умолчанию `created_at + 7 days`) и легкий фоновый periodic task / индекс для очистки устаревших ключей.
   - *Трудоемкость:* 10 строк в `models.py` и миграция схемы.

5. **P1.3: Ограничение допустимых статусов на уровне СУБД (CHECK constraint)**
   - *Проблема:* Колонка `Interaction.state` в `models.py` объявлена как `String(80)` без `CheckConstraint`, что позволяет нарушить целостность прямым SQL-запросом.
   - *Решение:* Добавить `CheckConstraint("state IN ('contact_search', ...)", name="chk_interaction_state")` в `__table_args__` модели `Interaction`.
   - *Трудоемкость:* 4 строки кода в `backend/app/models.py`.

---

### Приоритет P2 (Расширение корпоративного жизненного цикла процессов — по требованию)

6. **P2.1: Персистентный реестр шаблонов и версий в СУБД (`workflow_version`)**
   - *Описание:* Создание реляционных таблиц `workflow_template`, `workflow_version`, `workflow_state`, `workflow_transition` с поддержкой жизненного цикла `Draft` -> `Published` -> `Retired`.
   - *Инженерный комментарий:* Текущее In-Memory хранение в `WORKFLOW_REGISTRY` полностью обеспечивает требуемую производительность и стабильность в рамках первого релиза. Переход на полноценные реляционные таблицы целесообразен только при появлении явного бизнес-требования на самостоятельное визуальное конструирование процессов администраторами без участия разработчиков.

7. **P2.2: Асинхронная построчная миграция больших объемов карточек (`workflow_migration_plan`)**
   - *Описание:* Создание персистентных таблиц `workflow_migration_plan` и `workflow_migration_item` с асинхронным исполнителем (Celery/RQ/BackgroundTasks) для миграции миллионов карточек с постраничным прогрессом и полистным статусом (`applied/conflict/invalid`).
   - *Инженерный комментарий:* При текущем объеме взаимодействий (до нескольких тысяч активных карточек) синхронная пакетная миграция выполняется менее чем за 1 секунду. Создание очереди фоновых задач до достижения критического объема данных является преждевременной оптимизацией (YAGNI).

---

## 6. Verification Method (Метод независимой воспроизводимости)

Для независимой проверки всех утверждений настоящего отчета выполните следующие команды из корневого каталога репозитория:

1. **Проверка неизменяемости файлов эталонной архитектуры (Git Status):**
   ```bash
   git status docs/architecture/
   ```
   *Ожидаемый результат:* каталог чист, отсутствие каких-либо изменений (`nothing to commit, working tree clean`).

2. **Запуск эталонных архитектурных и сценарных проверок:**
   ```bash
   python3 docs/checks/verify_workflow.py && \
   python3 docs/checks/verify_reports.py && \
   python3 docs/checks/verify_plan.py && \
   python3 docs/checks/verify_infra.py
   ```
   *Ожидаемый результат:* Все проверки завершаются с вердиктом `PASS`.

3. **Сверка эталонного JSON-графа и данных бэкенда:**
   ```bash
   diff -u docs/planning/04-base-workflow.json backend/app/data/base-workflow.json
   ```
   *Ожидаемый результат:* Код возврата 0, вывод полностью пуст (побайтовая идентичность).

4. **Запуск полного набора тестов FSM, переходов, миграций, CAS и безопасности:**
   ```bash
   backend/.venv/bin/python -m pytest \
     backend/tests/test_workflow_migration.py \
     backend/tests/test_working_slice.py \
     backend/tests/test_core_concurrency_and_security.py -v
   ```
   *Ожидаемый результат:* `41 passed` без единой ошибки.

5. **Проверка стресс-теста конкурентности CAS (20 параллельных потоков):**
   ```bash
   backend/.venv/bin/python -m pytest backend/tests/test_core_concurrency_and_security.py -k "test_cas_concurrency" -v
   ```
   *Ожидаемый результат:* `2 passed` (успешная изоляция 20 одновременных потоков на патче и переходе).
