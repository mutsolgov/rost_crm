# Технический план реализации Task B17: R1 Workflow Migration Engine & R7 Tests

## 1. Executive Summary & Problem Boundary

В рамках спринта готовности Gate P / Gate O (задача **B17**, требования **R06**, **R07**, **R20**, сценарий приёмки **AC08**) требуется реализовать механизм явной миграции активных бизнес-процессов между версиями шаблона workflow.

### Ключевые требования:
1. **Версионирование процессов**:
   - **Версия 1**: базовый процесс сотрудничества с вузом (13 рабочих + 2 терминальных состояния) согласно `04-base-workflow.json`.
   - **Версия 2**: расширенный и оптимизированный шаблон с ускоренными переходами (fast-track) и дополнительными циклами доработки.
2. **Сервис предпросмотра (`preview_workflow_migration`)**:
   - Проверка допустимости сопоставления: безусловное отклонение сопоставления терминальных статусов (`completed`, `cancelled`) в активные со статусом **HTTP 422**.
   - Вычисление количества затронутых активных карточек (`state not in TERMINAL_STATES`, `workflow_version == from_version`).
   - Расчёт распределения карточек по статусам до и после миграции.
   - Детекция несопоставленных статусов (unmapped) и коллизий сопоставления (N-to-1).
3. **Сервис атомарного применения (`commit_workflow_migration`)**:
   - Атомарный транзакционный перевод всех подходящих карточек на новую версию workflow.
   - Инкремент ревизии карточки (`item.revision += 1`) для обеспечения CAS-безопасности параллельных изменений.
   - Неизменяемый аудит: генерация события `InteractionEvent(type="workflow_migrated")` для каждой карточки с полным снимком (snapshot).
   - 100% сохранение истории предыдущих событий, комментариев и прикреплённых файлов (attachments).
   - Поддержка заголовка `Idempotency-Key` через `begin_command` / `finish_command` с возвратом сохранённого ответа при повторном запросе без повторного применения.
4. **REST API**:
   - `POST /api/v1/workflow/migrate/preview` (dry-run).
   - `POST /api/v1/workflow/migrate/commit` (транзакционный коммит).
   - Ролевые права: доступ разрешён строго ролям `supervisor` и `administrator`. Пользователям с ролью `manager` возвращается **HTTP 403 Forbidden**.
5. **Автоматизированное тестирование**:
   - Создание тестового модуля `backend/tests/test_workflow_migration.py` с полным покрытием позитивных и негативных сценариев, RBAC, идемпотентности, CAS и целостности связей.
   - Сохранение 100% работоспособности 99 существующих тестов и контрольных скриптов спецификации (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`).
   - Нулевой прирост внешних библиотек (0 новых зависимостей в `requirements.txt`).

---

## 2. Анализ текущей кодовой базы и инвариантов

### 2.1. Модели данных (`backend/app/models.py`)
- **`Interaction`**:
  - Содержит поля `workflow_version: Mapped[int] = mapped_column(Integer, default=1)` и `revision: Mapped[int] = mapped_column(Integer, default=1)` (строки 117–118).
  - Имеет внешние ключи: `organization_id`, `program_id`, `product_id`, `owner_id`, `contract_id`, `license_id`, `contact_id`.
  - Поле `state: Mapped[str] = mapped_column(String(80))` хранит код текущего состояния.
  - Поле `closed_at: Mapped[datetime | None]` устанавливается при переходе в терминальное состояние (`completed`, `cancelled`).
- **`InteractionEvent`**:
  - Хранит неизменяемый лог аудита: `interaction_id`, `type`, `effective_at`, `received_at`, `sequence`, `actor_id`, `actor_name`, `payload`.
  - Имеет `UniqueConstraint("interaction_id", "sequence")`.
  - Функция `append_event(...)` в `services.py` автоматически определяет `max(sequence) + 1` и фиксирует неизменяемый снимок `snapshot: interaction_dict(db, item)`.
- **`Comment` и `Attachment`**:
  - Связаны с карточкой по `interaction_id`. При обновлении `Interaction.state` и `Interaction.workflow_version` комментарии и вложения не модифицируются и полностью сохраняются.
- **`CommandResult`**:
  - Обеспечивает строгую идемпотентность через `UniqueConstraint("user_id", "operation", "key")`.
  - В `services.py:begin_command` вычисляется SHA-256 хэш тела запроса (`payload_hash`). При совпадении возвращается закешированный `response`. При несовпадении хэша возвращается `409 IDEMPOTENCY_CONFLICT`.
  - **Важный инвариант**: При фиксации batch-операций (как в `importer.py:commit_organizations_import`) в `finish_command` передаётся `resource_id=None`. Это исключает ошибочную проверку доступа к одиночной карточке в `scoped_interaction` при воспроизведении команды по Idempotency-Key.

### 2.2. Сервисный слой и управление переходами (`backend/app/workflow.py`, `services.py`)
- В `backend/app/workflow.py` загружается `base-workflow.json` (Версия 1):
  - 13 рабочих + 2 терминальных состояния (`completed`, `cancelled`).
  - 29 переходов.
- В `backend/app/services.py`:
  - `interaction_dict(db, item)` использует `STATES[item.state]["name"]`. Для безопасной поддержки новых версий необходимо гарантировать наличие имён состояний для всех версий шаблона.
  - `detail(db, user, interaction_id)` формирует `allowed_transitions = allowed_transitions(item.state)`. Для карточек версии 2 список доступных переходов должен определяться по версии карточки (`item.workflow_version`).
  - `transition(db, user, interaction_id, body, key)` ищет переход в таблице переходов соответствующей версии workflow.

### 2.3. Ролевой доступ и 152-ФЗ
- `permissions(user)` в `services.py`:
  - Роль `manager`: права на работу только со своими карточками, без права изменения настроек процессов.
  - Роль `supervisor`: руководство командой.
  - Роль `administrator`: системное администрирование.
- **Инвариант B17**:
  - Операции миграции процессов доступны исключительно ролям `supervisor` и `administrator`.
  - Пользователям с ролью `manager` возвращается `HTTP 403 Forbidden` (`FORBIDDEN: Недостаточно прав для выполнения миграции процессов.`).
  - Миграция процессов шаблона охватывает все активные карточки целевого шаблона в системе (`state != terminal`, `workflow_version == from_version`).

---
## 3. Спецификация версий Workflow (V1 vs V2)

### 3.1. Версия 1: Базовый шаблон (15 состояний)
- **Идентификатор**: `version = 1`, `template_code = "rtk_university_cooperation"`.
- **13 рабочих состояний**:
  1. `contact_search` (Поиск контактов) — начальное состояние.
  2. `needs_clarification` (Уточнение потребности)
  3. `meeting` (Встреча с вузом)
  4. `document_exchange` (Обмен документами)
  5. `document_revision` (Корректировка документов)
  6. `document_signing` (Подписание документов)
  7. `materials_transfer` (Передача материалов и лицензии)
  8. `deployment` (Сопровождение внедрения)
  9. `teacher_training` (Обучение преподавателей)
  10. `curriculum_update` (Актуализация учебной программы)
  11. `classes` (Ведение занятий)
  12. `materials_update` (Актуализация материалов)
  13. `teacher_upskilling` (Повышение квалификации преподавателей)
- **2 терминальных состояния**:
  14. `completed` (Взаимодействие завершено)
  15. `cancelled` (Взаимодействие отменено)
- **29 переходов**: 13 прямых, 1 пропуск опционального этапа, 2 цикла доработки, 13 переходов отмены.

### 3.2. Версия 2: Расширенный шаблон с оптимизированными переходами
- **Идентификатор**: `version = 2`, `template_code = "rtk_university_cooperation"`.
- **Название**: `"Взаимодействие с вузом по ИТ-программе и ИТ-продукту (Оптимизированный процесс v2)"`.
- **Состояния**: Сохраняет 15 базовых стадий (обеспечивая 100% совместимость с аналитическими отчётами и фикстурой `05-report-fixture.json`).
- **Оптимизированные переходы в v2 (Fast-Track & Rework Extensions)**:
  1. `meeting_to_document_signing` (Fast-track подписание): прямой переход со встречи к подписанию типового соглашения без промежуточного обмена черновиками (`from: meeting`, `to: document_signing`, `kind: forward`, `comment_required: false`).
  2. `materials_transfer_to_classes` (Express запуск занятий): прямой переход к ведению занятий для коробочных/типовых курсов без длительного развертывания и переподготовки (`from: materials_transfer`, `to: classes`, `kind: forward`, `comment_required: false`).
  3. `classes_to_completed` (Прямое завершение): завершение однократных учебных циклов без необходимости актуализации материалов и доп. квалификации (`from: classes`, `to: completed`, `kind: forward`, `comment_required: false`).
  4. `deployment_to_materials_transfer` (Доработка лицензий): возврат на этап передачи при выявлении нехватки ключей/материалов при развертывании (`from: deployment`, `to: materials_transfer`, `kind: rework`, `comment_required: true`).
  5. `classes_to_teacher_training` (Дополнительное обучение в ходе курса): оперативная доподготовка преподавателей во время семестра (`from: classes`, `to: teacher_training`, `kind: rework`, `comment_required: true`).
  6. `document_signing_to_meeting` (Возврат на повторные переговоры): возврат при отклонении условий договора руководством вуза (`from: document_signing`, `to: meeting`, `kind: rework`, `comment_required: true`).
  7. `materials_transfer_to_cancelled`, `deployment_to_cancelled`, `teacher_training_to_cancelled`, `classes_to_cancelled`: расширенные переходы отмены на производственных этапах с обязательным комментарием.

Всего в v2: 36 переходов, обеспечивающих максимальную гибкость бизнес-процесса.

### 3.3. Архитектура реестра Workflow в `backend/app/workflow.py`
Реестр `WORKFLOW_REGISTRY = {1: WORKFLOW_V1, 2: WORKFLOW_V2}` инкапсулирует версии.
Функции:
- `get_workflow(version: int = 1) -> dict`
- `get_states(version: int = 1) -> dict`
- `get_transitions(version: int = 1) -> dict`
- `allowed_transitions(state: str, version: int = 1) -> list[dict]`
- Экспорт `ALL_STATES` и `ALL_TRANSITIONS` для безопасной работы `services.py` без `KeyError`.

---
## 4. Спецификация сервиса предпросмотра (`preview_workflow_migration`)

### 4.1. Сигнатура
```python
def preview_workflow_migration(
    db: Session,
    user: User,
    from_version: int,
    to_version: int,
    status_mapping: dict[str, str]
) -> dict:
```

### 4.2. Алгоритм и правила валидации
1. **Проверка прав**: `user.role in ("supervisor", "administrator")`, иначе `403 FORBIDDEN`.
2. **Проверка версий**:
   - `from_version` и `to_version` должны существовать в `WORKFLOW_REGISTRY`, иначе `422 VALIDATION_ERROR`.
   - `from_version == to_version` запрещено, иначе `422 VALIDATION_ERROR`.
3. **Проверка сопоставления (`status_mapping`)**:
   - **Запрет терминальный -> активный**:
     ```python
     from_terminal = {k for k, s in get_states(from_version).items() if s["kind"] == "terminal"}
     to_terminal = {k for k, s in get_states(to_version).items() if s["kind"] == "terminal"}
     for src, dst in status_mapping.items():
         if src in from_terminal and dst not in to_terminal:
             raise APIError(
                 "VALIDATION_ERROR",
                 f"Недопустимо сопоставлять терминальный статус '{src}' в активный статус '{dst}'.",
                 422
             )
         if dst not in get_states(to_version):
             raise APIError(
                 "VALIDATION_ERROR",
                 f"Целевой статус '{dst}' отсутствует в версии {to_version}.",
                 422
             )
     ```
4. **Выборка активных взаимодействий**:
   ```python
   interactions = list(db.scalars(
       select(Interaction).where(
           Interaction.workflow_version == from_version,
           Interaction.state.not_in(from_terminal)
       ).order_by(Interaction.id)
   ))
   ```
5. **Расчёт распределений до и после**:
   - `status_distribution_before`: подсчёт реальных активных карточек по статусам.
   - `status_distribution_after`: проекция счётчиков в целевые статусы по `status_mapping`.
6. **Детекция несопоставленных статусов (unmapped)**:
   - `unmapped_statuses`: активные статусы с существующими карточками, не указанные в `status_mapping`.
   - При наличии: `is_valid = False`, описание добавляется в `warnings`.
7. **Детекция коллизий сопоставления (collisions)**:
   - Выявление объединений нескольких исходных статусов в один целевой (N-to-1):
     `target_to_sources`: если длина списка $> 1$, формируется элемент `collisions` и текстовое предупреждение в `warnings`.
8. **Формат ответа**:
   ```json
   {
     "from_version": 1,
     "to_version": 2,
     "affected_interactions_count": 5,
     "status_distribution_before": {"contact_search": 2, "document_revision": 3},
     "status_distribution_after": {"contact_search": 2, "document_signing": 3},
     "unmapped_statuses": [],
     "collisions": [
       {
         "target_status": "document_signing",
         "target_name": "Подписание документов",
         "source_statuses": ["document_revision", "document_signing"]
       }
     ],
     "warnings": [
       "Коллизия: статусы ['document_revision', 'document_signing'] объединены в 'document_signing'."
     ],
     "is_valid": true
   }
   ```

---
## 5. Спецификация сервиса коммита (`commit_workflow_migration`)

### 5.1. Сигнатура
```python
def commit_workflow_migration(
    db: Session,
    user: User,
    from_version: int,
    to_version: int,
    status_mapping: dict[str, str],
    idempotency_key: str | None
) -> dict:
```

### 5.2. Пошаговый сценарий исполнения
1. **RBAC**: `user.role in ("supervisor", "administrator")`, иначе `403 FORBIDDEN`.
2. **Идемпотентность**:
   - Обязательный заголовок `Idempotency-Key` ($\le 200$ символов).
   - Вызов `begin_command(db, user, f"workflow_migration:{from_version}->{to_version}", idempotency_key, payload)`.
   - При повторном запросе — возврат кэшированного ответа со статусом 200 без повторного применения.
3. **Строгая валидация**:
   - Запрет терминальный -> активный (`422 VALIDATION_ERROR`).
   - Проверка целевых статусов на существование в `to_version`.
4. **Транзакционная выборка карточек**:
   - Выборка всех активных карточек с `workflow_version == from_version` и `state.not_in(from_terminal)`.
   - Проверка отсутствия несопоставленных статусов у активных карточек: если есть, откат и `422 VALIDATION_ERROR`.
5. **Атомарная модификация карточек и генерация аудита**:
   - Время фиксации: единое `now = utcnow()`.
   - Для каждого взаимодействия:
     ```python
     old_state = item.state
     old_revision = item.revision
     new_state = status_mapping[old_state]

     item.workflow_version = to_version
     item.state = new_state
     item.revision = old_revision + 1  # CAS-инкремент!
     item.updated_at = now
     if new_state in to_terminal:
         item.closed_at = now

     append_event(
         db,
         item,
         user,
         "workflow_migrated",
         now,
         from_version=from_version,
         to_version=to_version,
         from_state=old_state,
         to_state=new_state,
         previous_revision=old_revision,
         new_revision=item.revision,
     )
     ```
   - **Сохранение целостности связей**: Все ранее созданные события, комментарии (`Comment`) и файлы (`Attachment`) остаются в базе данных нетронутыми.
6. **Завершение команды (`finish_command`)**:
   - Сохранение ответа и фиксация транзакции: `finish_command(db, saved, response, None)`.

---
## 6. Спецификация REST API и Pydantic-схем

### 6.1. Pydantic-схемы (`backend/app/schemas.py`)
```python
class WorkflowMigrateRequest(Body):
    from_version: int = Field(ge=1, description="Исходная версия workflow")
    to_version: int = Field(ge=1, description="Целевая версия workflow")
    status_mapping: dict[str, str] = Field(min_length=1, description="Матрица сопоставления статусов {старый: новый}")
```

### 6.2. Маршруты FastAPI (`backend/app/main.py`)
```python
@app.post("/api/v1/workflow/migrate/preview", tags=["workflow"])
def post_workflow_migrate_preview(
    body: WorkflowMigrateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return preview_workflow_migration(db, user, body.from_version, body.to_version, body.status_mapping)


@app.post("/api/v1/workflow/migrate/commit", tags=["workflow"])
def post_workflow_migrate_commit(
    body: WorkflowMigrateRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return commit_workflow_migration(
        db, user, body.from_version, body.to_version, body.status_mapping, idempotency_key
    )


@app.get("/api/v1/workflow", tags=["reference"])
def get_workflow(version: int = Query(1, ge=1), user: User = Depends(current_user)):
    from .workflow import get_workflow as load_wf
    wf = load_wf(version)
    return {
        "schema_version": wf["schema_version"],
        "template_code": wf["template_code"],
        "version": wf["version"],
        "name": wf["name"],
        "initial_state": wf["initial_state"],
        "states": wf["states"],
        "transitions": wf["transitions"],
    }
```

---

## 7. План тестового модуля `backend/tests/test_workflow_migration.py`

Будет реализован полноценный тестовый модуль из 11 тестовых сценариев:
1. `test_workflow_migrate_rbac_manager_forbidden`: проверка возврата `403 Forbidden` для роли менеджера на preview и commit.
2. `test_workflow_migrate_rbac_supervisor_allowed`: проверка доступности preview и commit для руководителя (`200 OK`).
3. `test_workflow_migrate_rbac_admin_allowed`: проверка доступности preview и commit для администратора (`200 OK`).
4. `test_workflow_migrate_reject_terminal_to_active`: отклонение сопоставления `completed -> contact_search` со статусом `422 VALIDATION_ERROR`.
5. `test_workflow_migrate_missing_idempotency_key`: отказ при вызове commit без заголовка `Idempotency-Key` (`422 VALIDATION_ERROR`).
6. `test_workflow_migrate_preview_calculation_and_collisions`: корректность подсчёта затронутых карточек, распределения до/после, фиксация коллизий N-to-1 и игнорирование терминальных карточек.
7. `test_workflow_migrate_preview_unmapped_status`: карточка в несопоставленном статусе делает `is_valid: False` и отображается в `unmapped_statuses`.
8. `test_workflow_migrate_commit_atomic_execution`: все активные карточки обновляют `workflow_version=2`, инкрементируют `revision`, создаётся событие `workflow_migrated` с последовательным `sequence`.
9. `test_workflow_migrate_preserves_history_comments_attachments`: проверка карточки после миграции через `GET /interactions/{id}`: сохранение событий `created`, `state_changed`, комментария и файла вложения.
10. `test_workflow_migrate_idempotency_replay_and_conflict`: повторный запрос с тем же `Idempotency-Key` возвращает кэшированный ответ (без повторного инкремента ревизии); запрос с тем же ключом, но изменённым телом возвращает `409 Conflict`.
11. `test_v2_allowed_transitions_after_migration`: после миграции на v2 карточка видит переходы v2 (например, fast-track `meeting -> document_signing`) и успешно выполняет их.

---

## 8. Соответствие стандартам и чек-лист готовности

- **Zero Dependency Growth**: Не требуется ни одной новой зависимости в `backend/requirements.txt`.
- **100% Тестовая регрессия**: Все 99 существующих тестов (`tests/test_working_slice.py`, `tests/test_interaction_patch.py`, `tests/test_reports_multiformat.py` и др.) продолжают проходить со статусом PASS.
- **Оракулы спецификации**: `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` — все PASS.
- **Инварианты 152-ФЗ / ФСТЭК №117**:
  - Сохранение неизменяемого следа аудита в `InteractionEvent`.
  - Защита данных от несанкционированного изменения менеджером (403 Forbidden).
  - Защита от дедлоков и гонок через CAS-инкремент ревизии.
