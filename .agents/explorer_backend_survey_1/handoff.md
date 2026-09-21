# Архитектурный отчёт и план реализации бэкенда (R1, R2, R4)

## 1. Observation (Фактические наблюдения)

### 1.1. Инфраструктура базы данных и регистрация моделей
- В `backend/app/db.py:41-43` определена функция инициализации схемы:
  ```python
  def init_db():
      from . import models  # Register model metadata; schema creation is explicit only.
      Base.metadata.create_all(get_engine())
  ```
- В проекте **отсутствует Alembic** (поиск по имени `*alembic*` вернул 0 результатов). Управление схемой в тестах (`backend/tests/conftest.py:19`) и локальной среде происходит декларативно через вызов `Base.metadata.create_all(engine)`.
- Движок SQLite настраивается с включением внешних ключей (`PRAGMA foreign_keys=ON`) и таймаута занятости (`PRAGMA busy_timeout=20000`) в `backend/app/db.py:27-28`.

### 1.2. Текущее состояние моделей (`backend/app/models.py`)
- В файле объявлены сущности: `User` (строки 18–27), `Organization` (строки 29–34), `OrganizationAccess` (строки 36–42), `Direction` (строки 44–48), `Program` (строки 50–55), `Product` (строки 57–62), `ProgramProduct` (строки 64–68), `Interaction` (строки 70–87), `InteractionEvent` (строки 89–104), `Comment` (строки 106–115), `CommandResult` (строки 117–128).
- **Дефицит сущностей R1**:
  - Модели `OrganizationContact`, `Contract`, `License`, `Attachment` отсутствуют.
  - В модели `Interaction` (строки 70–87) отсутствуют внешние ключи `contract_id`, `license_id`, `contact_id`.
  - Уникальный идентификатор генерируется функцией `new_id() = str(uuid4())`, таймштампы — `utcnow() = datetime.now(timezone.utc)`.

### 1.3. Сериализация каталогов и карточки (`backend/app/services.py`)
- В `backend/app/services.py:273-291` метод `catalogs(db, user)` возвращает словарь со списками: `"organizations"`, `"programs"`, `"products"`, `"owners"`, `"directions"`. Списки договоров, лицензий и контактов вузов не запрашиваются и не возвращаются.
- В `backend/app/services.py:89-105` функция `interaction_dict(db, item)` сериализует только:
  `id`, `title`, `organization_id`, `organization_name`, `program_id`, `program_name`, `product_id`, `product_name`, `direction_name`, `cycle_label`, `owner_id`, `owner_name`, `state`, `state_name`, `workflow_version`, `revision`, `created_at`, `updated_at`, `closed_at`.
  Поля `contact_id`, `contact_name`, `contract_id`, `contract_number`, `license_id`, `license_status` отсутствуют.

### 1.4. Дедлок D02 и механизм переходов
- В `backend/app/workflow.py:9-12`:
  ```python
  SUBJECT_REQUIRED_STATES = {
      "materials_transfer", "deployment", "teacher_training", "curriculum_update", "classes",
      "materials_update", "teacher_upskilling", "completed",
  }
  ```
- В `backend/app/services.py:226-228` (`transition`):
  ```python
  if edge["to"] in SUBJECT_REQUIRED_STATES and (not item.program_id or not item.product_id):
      raise APIError("VALIDATION_ERROR", "Перед этим этапом укажите ИТ-программу и ИТ-продукт.")
  ```
- В `backend/tests/test_working_slice.py:140-154` тест `test_missing_program_and_product_prevent_late_stage` подтверждает: карточка без `program_id`/`product_id` доходит до `document_signing`, но переход в `materials_transfer` блокируется со статусом 422. В текущем API нет способа отредактировать атрибуты существующей карточки, поэтому она навсегда зависает на этапе `document_signing` (Дедлок D02).

### 1.5. Логика CAS, Idempotency-Key и транзакций
- **Idempotency**: `begin_command(db, user, operation, key, payload)` (`services.py:147-173`) проверяет длину ключа (1–200 символов), вычисляет SHA-256 хеш канонического JSON-представления `payload`, проверяет запись `CommandResult` по `(user_id, operation, key)`. При повторном запросе возвращает сохранённый `response`, при несовпадении хеша — 409 `IDEMPOTENCY_CONFLICT`.
- **CAS update**: `cas(db, item, expected_revision, **values)` (`services.py:181-190`):
  ```python
  result = db.execute(update(Interaction).where(Interaction.id == item.id,
                     Interaction.revision == expected_revision).values(
                         revision=expected_revision + 1, **values),
                     execution_options={"synchronize_session": False})
  if result.rowcount != 1:
      db.rollback()
      raise APIError("REVISION_CONFLICT", "Карточка изменена. Обновите данные.", 409)
  db.refresh(item)
  ```
  Инкрементирует `revision` атомарным SQL-запросом. При конфликте версий возвращает 409 `REVISION_CONFLICT`.
- **Фиксация команды**: `finish_command(db, saved, response, resource_id)` (`services.py:175-179`) сохраняет результат и выполняет `db.commit()`.

### 1.6. Разграничение доступа (152-ФЗ / Scope Clause)
- В `backend/app/services.py:39-52`:
  - `scope_clause(user)` объединяет условия:
    - Менеджер: `Interaction.owner_id == user.id`
    - Руководитель: `Interaction.team_id == user.team_id`
    - Явный грант: `Interaction.organization_id.in_(granted)` где `read_all.is_(True)`
  - `scoped_interaction(db, user, interaction_id)` выполняет:
    ```python
    interaction = db.scalar(select(Interaction).where(Interaction.id == interaction_id, scope_clause(user)))
    if not interaction:
        raise APIError("NOT_FOUND", "Взаимодействие не найдено.", 404)
    return interaction
    ```
  - Попытка доступа к чужой карточке возвращает `404 Not Found`, что исключает утечку информации о существовании записи.
- В `backend/app/services.py:24-31` функция `permissions(user)` возвращает:
  - `manager`: `{"interactions.create", "interactions.transition", "interactions.comment", "reports.read"}`
  - `supervisor`: `{"interactions.create", "interactions.transition", "interactions.comment", "interactions.assign", "reports.read", "organizations.create"}`
  - Разрешение `"interactions.edit"` на данный момент не включено в список прав по умолчанию.

### 1.7. Инварианты данных в `backend/app/seed.py`
- В `backend/app/seed.py:82-95` зафиксированы гранты:
  ```python
  grants = {
      ("manager-a", "org-1"): (True, False),
      ("manager-b", "org-2"): (True, False),
      ("supervisor", "org-1"): (True, True),
      ("supervisor", "org-2"): (True, True),
      ("supervisor", "org-3"): (True, True),
  }
  ```
- Значение `read_all=False` для `manager-a` и `manager-b` критично: если бы `read_all` было `True`, то после переназначения карточки руководителем старому менеджеру карточка всё равно оставалась бы видна через грант организации.

### 1.8. Результаты прогона существующих тестов и проверок
- Команда запуска тестов:
  `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_working_slice.py`
  Результат: **17 passed, 2 warnings in 3.55s**.
- Команды валидации спецификации:
  - `backend/.venv/bin/python docs/checks/verify_workflow.py` -> PASS (13 working states, 2 terminal states, 29 transitions)
  - `backend/.venv/bin/python docs/checks/verify_reports.py` -> PASS (12 exact report cases verified)
  - `backend/.venv/bin/python docs/checks/verify_plan.py` -> PASS (40 tasks, no dependency cycles)

---

## 2. Logic Chain (Логическая цепочка)

```
[Observation 1.2: Отсутствуют Contract, License, OrganizationContact, Attachment]
  ├──> Требуется расширить models.py сущностями по ТЗ (стр. 4) и ADR 002
  └──> Расширить модель Interaction внешними ключами contact_id, contract_id, license_id

[Observation 1.1: Base.metadata.create_all создает схему автоматически]
  └──> Добавление моделей в models.py не требует написания ручных миграций Alembic:
       схема в SQLite генерируется на лету при старте тестов/приложения

[Observation 1.3: catalogs() и interaction_dict() не сериализуют новые сущности]
  ├──> catalogs() должен делать выборку контактов, договоров и лицензий для visible_organization_ids(db, user)
  └──> interaction_dict() должен обогащать словарь полями contact_name, contract_number, license_status

[Observation 1.4: Дедлок D02 на этапе document_signing -> materials_transfer]
  ├──> Карточка, созданная без программы/продукта, блокируется на SUBJECT_REQUIRED_STATES
  ├──> Требуется маршрут PATCH /api/v1/interactions/{id} с поддержкой обновления program_id и product_id
  └──> После применения PATCH с валидными программой/продуктом переход в materials_transfer разблокируется (AC07)

[Observation 1.5: Архитектура CAS и Idempotency через begin_command / finish_command]
  ├──> Метод PATCH /api/v1/interactions/{id} обязан следовать общему паттерну:
  │    1. scoped_interaction(db, user, interaction_id) -> 404 при чужом ID
  │    2. require_permission(user, "interactions.edit") -> 403 при нехватке прав
  │    3. begin_command(db, user, f"update:{item.id}", key, body.model_dump()) -> идемпотентность
  │    4. Проверка инвариантов (SUBJECT_REQUIRED_STATES, validate_subject, валидация принадлежности contact/contract/license)
  │    5. cas(db, item, body.expected_revision, **updates) -> 409 при конфликте ревизий
  │    6. append_event(db, item, user, "attributes_corrected", now, changes=changes) -> аудит
  │    7. finish_command(db, saved, interaction_dict(db, item), item.id)
  └──> Идемпотентный повтор гарантированно не создает дублирующих событий в InteractionEvent

[Observation 1.6 & 1.7: Ролевая изоляция данных и инвариант seed.py]
  ├──> Менеджер видит только карточки со своим owner_id (read_all=False в seed.py)
  ├──> При попытке менеджера Б выполнить PATCH карточки менеджера А scoped_interaction бросает 404
  └──> Переназначение карточки руководителем новому менеджеру немедленно закрывает доступ для старого (404)
```

---

## 3. Caveats (Ограничения и нюансы реализации)

1. **Обработка частичного обновления (Partial Update) в Pydantic v2**:
   В `InteractionUpdate` все поля, кроме `expected_revision`, являются опциональными (`default=None`).
   Для предотвращения затирания существующих полей значениями `None` при обновлении, логика сервиса должна использовать `body.model_fields_set`. Поле обновляется только если оно явно передано клиентом в запросе.
2. **Запрет сброса в `None` на поздних этапах**:
   Если карточка находится в `SUBJECT_REQUIRED_STATES` (`materials_transfer` и далее), попытка передать `program_id=None` или `product_id=None` должна отклоняться с кодом 422 `VALIDATION_ERROR`.
3. **Неизменяемость завершённых карточек**:
   Если `item.closed_at` не пустой (терминальные статусы `completed`, `cancelled`), вызов PATCH должен возвращать 422 `VALIDATION_ERROR` ("Завершённое взаимодействие не подлежит изменению"), по аналогии с `assign`.
4. **Валидация ссылочной целостности организации**:
   Если в PATCH переданы `contact_id`, `contract_id` или `license_id`, они должны принадлежать той же организации, к которой привязана карточка (`item.organization_id`). При несовпадении — 422 `VALIDATION_ERROR`.
5. **Лицензия и продукт**:
   Если карточка имеет `product_id` и указывается `license_id`, необходимо убедиться, что `license.product_id == item.product_id`.
6. **Права доступа**:
   В `services.py:permissions()` необходимо добавить `"interactions.edit"` в наборы по умолчанию для ролей `"manager"` и `"supervisor"`.

---

## 4. Conclusion & Concrete Blueprint (Архитектурный план и спецификация кода)

### 4.1. Спецификация для R1 (Модели, Каталоги, Сериализация, Seed)

#### А. Модели данных (`backend/app/models.py`)
Добавить классы:
```python
class OrganizationContact(Base):
    __tablename__ = "organization_contacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(250))
    position: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    number: Mapped[str] = mapped_column(String(100))
    signed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class License(Base):
    __tablename__ = "licenses"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"), index=True, nullable=True)
    signed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    term_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transfer_status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    interaction_id: Mapped[str] = mapped_column(ForeignKey("interactions.id"), index=True)
    visit_id: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

В класс `Interaction` добавить колонки:
```python
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"), index=True, nullable=True)
    license_id: Mapped[str | None] = mapped_column(ForeignKey("licenses.id"), index=True, nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("organization_contacts.id"), index=True, nullable=True)
```

#### Б. Сериализация каталогов и карточки (`backend/app/services.py`)
1. **Обновление `permissions()`**:
   ```python
   def permissions(user):
       defaults = {
           "manager": {"interactions.create", "interactions.transition", "interactions.comment",
                       "interactions.edit", "reports.read"},
           "supervisor": {"interactions.create", "interactions.transition", "interactions.comment",
                          "interactions.assign", "interactions.edit", "reports.read", "organizations.create"},
           "administrator": {"workflow.manage", "users.manage", "organizations.create", "reports.read"},
       }
       return sorted(defaults.get(user.role, set()) | set(user.permissions or []))
   ```

2. **Обновление `catalogs(db, user)`**:
   ```python
   def catalogs(db, user):
       org_ids = visible_organization_ids(db, user)
       orgs = list(db.scalars(select(Organization).where(Organization.id.in_(org_ids)).order_by(Organization.name)))
       owner_ids = set(db.scalars(select(Interaction.owner_id).where(scope_clause(user))))
       owner_ids.add(user.id)
       if user.role == "supervisor":
           owner_ids.update(db.scalars(select(User.id).where(User.team_id == user.team_id, User.role == "manager")))
       owners = db.scalars(select(User).where(User.id.in_(owner_ids), User.active.is_(True)).order_by(User.name))
       directions = {d.id: d for d in db.scalars(select(Direction).order_by(Direction.name))}
       contacts = list(db.scalars(select(OrganizationContact).where(
           OrganizationContact.organization_id.in_(org_ids), OrganizationContact.active.is_(True)).order_by(OrganizationContact.full_name)))
       contracts = list(db.scalars(select(Contract).where(
           Contract.organization_id.in_(org_ids)).order_by(Contract.number)))
       licenses = list(db.scalars(select(License).where(
           License.organization_id.in_(org_ids)).order_by(License.created_at.desc())))
       return {
           "organizations": [{"id": o.id, "name": o.name, "type": o.type} for o in orgs],
           "programs": [{"id": p.id, "name": p.name, "direction_id": p.direction_id,
                         "direction_name": directions[p.direction_id].name}
                        for p in db.scalars(select(Program).order_by(Program.name))],
           "products": [{"id": p.id, "name": p.name, "vendor": p.vendor}
                        for p in db.scalars(select(Product).order_by(Product.name))],
           "owners": [{"id": o.id, "name": o.name} for o in owners],
           "directions": [{"id": d.id, "name": d.name} for d in directions.values()],
           "contacts": [{"id": c.id, "organization_id": c.organization_id, "full_name": c.full_name,
                         "position": c.position, "email": c.email, "phone": c.phone, "active": c.active}
                        for c in contacts],
           "contracts": [{"id": c.id, "organization_id": c.organization_id, "number": c.number,
                          "signed_on": iso(c.signed_on), "status": c.status, "created_at": iso(c.created_at)}
                         for c in contracts],
           "licenses": [{"id": l.id, "organization_id": l.organization_id, "product_id": l.product_id,
                         "contract_id": l.contract_id, "signed_on": iso(l.signed_on), "term_years": l.term_years,
                         "transfer_status": l.transfer_status, "created_at": iso(l.created_at)}
                        for l in licenses],
       }
   ```

3. **Обновление `interaction_dict(db, item)`**:
   ```python
   def interaction_dict(db, item):
       org = db.get(Organization, item.organization_id)
       owner = db.get(User, item.owner_id)
       program = db.get(Program, item.program_id) if item.program_id else None
       product = db.get(Product, item.product_id) if item.product_id else None
       direction = db.get(Direction, program.direction_id) if program else None
       contact = db.get(OrganizationContact, item.contact_id) if item.contact_id else None
       contract = db.get(Contract, item.contract_id) if item.contract_id else None
       license_ = db.get(License, item.license_id) if item.license_id else None
       return {
           "id": item.id, "title": item.title, "organization_id": item.organization_id,
           "organization_name": org.name, "program_id": item.program_id,
           "program_name": program.name if program else None, "product_id": item.product_id,
           "product_name": product.name if product else None,
           "direction_name": direction.name if direction else None,
           "contact_id": item.contact_id, "contact_name": contact.full_name if contact else None,
           "contract_id": item.contract_id, "contract_number": contract.number if contract else None,
           "license_id": item.license_id, "license_status": license_.transfer_status if license_ else None,
           "cycle_label": item.cycle_label, "owner_id": item.owner_id, "owner_name": owner.name,
           "state": item.state, "state_name": STATES[item.state]["name"],
           "workflow_version": item.workflow_version, "revision": item.revision,
           "created_at": iso(item.created_at), "updated_at": iso(item.updated_at), "closed_at": iso(item.closed_at),
       }
   ```

4. **Обновление `event_dict(event)`**:
   В `event_dict` добавить извлечение `"changes"`:
   ```python
   def event_dict(event):
       result = {"id": event.id, "type": event.type, "effective_at": iso(event.effective_at),
                 "received_at": iso(event.received_at), "sequence": event.sequence, "actor_name": event.actor_name}
       for key in ("from_state", "to_state", "owner_id", "comment", "changes"):
           if key in event.payload:
               result[key] = event.payload[key]
       return result
   ```

#### В. Демо-данные в `backend/app/seed.py`
Добавить создание:
- Контактов: `contact-1` и `contact-2` для `org-1`, `contact-3` для `org-2`, `contact-4` для `org-3`.
- Договоров: `contract-1` для `org-1`, `contract-2` для `org-2`, `contract-3` для `org-3`.
- Лицензий: `license-1` и `license-2` для `org-1`, `license-3` и `license-4` для `org-2`.
- Привязать созданные контакты, договоры и лицензии к синтетическим карточкам `ix-1` – `ix-6`.
- Сохранить инвариант доступа:
  `("manager-a", "org-1"): (True, False)`, `("manager-b", "org-2"): (True, False)`.

---

### 4.2. Спецификация для R2 (Схема, Метод PATCH, CAS, Аудит-лог)

#### А. Pydantic-схема в `backend/app/schemas.py`
```python
class InteractionUpdate(Body):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=250)
    program_id: str | None = None
    product_id: str | None = None
    cycle_label: str | None = Field(default=None, min_length=1, max_length=100)
    contract_id: str | None = None
    license_id: str | None = None
    contact_id: str | None = None
```
Также расширить `InteractionCreate` опциональными полями:
```python
class InteractionCreate(Body):
    title: str = Field(min_length=1, max_length=250)
    organization_id: str = Field(min_length=1, max_length=64)
    program_id: str | None = None
    product_id: str | None = None
    cycle_label: str = Field(min_length=1, max_length=100)
    owner_id: str = Field(min_length=1, max_length=64)
    contact_id: str | None = None
    contract_id: str | None = None
    license_id: str | None = None
```

#### Б. Бизнес-логика `update_interaction` в `backend/app/services.py`
```python
def update_interaction(db, user, interaction_id, body, key):
    item = scoped_interaction(db, user, interaction_id)
    require_permission(user, "interactions.edit")
    if item.closed_at:
        raise APIError("VALIDATION_ERROR", "Завершённое взаимодействие не подлежит изменению.")
    saved, replay = begin_command(db, user, f"update:{item.id}", key, body.model_dump())
    if replay is not None:
        return replay

    new_program_id = body.program_id if "program_id" in body.model_fields_set else item.program_id
    new_product_id = body.product_id if "product_id" in body.model_fields_set else item.product_id
    new_contact_id = body.contact_id if "contact_id" in body.model_fields_set else item.contact_id
    new_contract_id = body.contract_id if "contract_id" in body.model_fields_set else item.contract_id
    new_license_id = body.license_id if "license_id" in body.model_fields_set else item.license_id
    new_title = body.title if "title" in body.model_fields_set else item.title
    new_cycle_label = body.cycle_label if "cycle_label" in body.model_fields_set else item.cycle_label

    if item.state in SUBJECT_REQUIRED_STATES and (new_program_id is None or new_product_id is None):
        raise APIError("VALIDATION_ERROR", "На этом этапе нельзя сбросить ИТ-программу или ИТ-продукт.")

    validate_subject(db, new_program_id, new_product_id)

    if new_contact_id:
        c = db.get(OrganizationContact, new_contact_id)
        if not c or c.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Контакт не принадлежит организации взаимодействия.")
    if new_contract_id:
        c = db.get(Contract, new_contract_id)
        if not c or c.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Договор не принадлежит организации взаимодействия.")
    if new_license_id:
        lic = db.get(License, new_license_id)
        if not lic or lic.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не принадлежит организации взаимодействия.")
        if new_product_id and lic.product_id != new_product_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует выбранному ИТ-продукту.")

    changes = {}
    updates = {}
    field_pairs = [
        ("title", new_title),
        ("cycle_label", new_cycle_label),
        ("program_id", new_program_id),
        ("product_id", new_product_id),
        ("contact_id", new_contact_id),
        ("contract_id", new_contract_id),
        ("license_id", new_license_id),
    ]
    for field, new_val in field_pairs:
        old_val = getattr(item, field)
        if old_val != new_val:
            changes[field] = {"old": old_val, "new": new_val}
            updates[field] = new_val

    now = utcnow()
    cas(db, item, body.expected_revision, updated_at=now, **updates)
    append_event(db, item, user, "attributes_corrected", now, changes=changes)
    return finish_command(db, saved, interaction_dict(db, item), item.id)
```

#### В. Маршрут в `backend/app/main.py`
```python
@app.patch("/api/v1/interactions/{interaction_id}", tags=["interactions"])
def patch_interaction(
    interaction_id: str,
    body: InteractionUpdate,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return update_interaction(db, user, interaction_id, body, idempotency_key)
```

---

### 4.3. Спецификация для R4 (Тестовый комплекс)

Создать файл `backend/tests/test_interaction_patch.py` со следующими тестами:

1. `test_patch_resolves_deadlock_d02(client)`:
   - Создать карточку без программы и продукта (`program_id=None, product_id=None`).
   - Пройти этапы до `document_signing`.
   - Попытка перехода в `materials_transfer` даёт 422 `VALIDATION_ERROR`.
   - Отправить `PATCH /api/v1/interactions/{id}` с `expected_revision=5`, `program_id="program-devops"`, `product_id="product-cloud"`.
   - Ответ 200 OK, `revision=6`, поля заполнены.
   - Повторить переход в `materials_transfer` с `expected_revision=6` -> 200 OK! (Доказательство устранения дедлока D02 / AC07).

2. `test_patch_disallows_clearing_subject_in_late_states(client)`:
   - На карточке в статусе `materials_transfer` попытаться отправить PATCH с `program_id=None`.
   - Получить отказ 422 `VALIDATION_ERROR`.

3. `test_patch_cas_conflict(client)`:
   - Создать карточку (ревизия 1).
   - Выполнить PATCH с устаревшей `expected_revision=99` (или 0).
   - Получить 409 `REVISION_CONFLICT`.

4. `test_patch_invalid_subject_combination(client)`:
   - Попытаться передать несовместимую пару `program-devops` и `product-test`.
   - Получить 422 `VALIDATION_ERROR`.

5. `test_patch_idempotency_and_event_sequence(client)`:
   - Отправить PATCH с `Idempotency-Key: test-key-1`.
   - Получить 200 OK.
   - Отправить повторный идентичный PATCH с тем же ключом.
   - Получить 200 OK с идентичным телом ответа.
   - Проверить `detail()["events"]`: событие `attributes_corrected` создано ровно 1 раз.
   - Отправить тот же ключ с другим телом -> получить 409 `IDEMPOTENCY_CONFLICT`.

6. `test_patch_scope_isolation_manager(client)`:
   - Менеджер А создал карточку.
   - Менеджер Б делает `PATCH /api/v1/interactions/{card_id}`.
   - Получить строго 404 `NOT_FOUND`.

7. `test_patch_scope_isolation_after_reassignment(client)`:
   - Менеджер А создал карточку.
   - Руководитель переназначил её на менеджера Б.
   - Менеджер А делает `PATCH /api/v1/interactions/{card_id}` -> строго 404 `NOT_FOUND`.

8. `test_patch_links_contact_contract_license(client)`:
   - Выполнить PATCH с передачей `contact_id`, `contract_id`, `license_id`.
   - Проверить 200 OK и наличие полей в `detail()`: `contact_name`, `contract_number`, `license_status`.
   - Попытка передать `contact_id` от другой организации возвращает 422 `VALIDATION_ERROR`.

9. `test_catalogs_returns_contracts_licenses_contacts(client)`:
   - Вызвать `GET /api/v1/catalogs`.
   - Проверить наличие непустых списков `contacts`, `contracts`, `licenses`.
   - Убедиться, что возвращаются только записи доступных организаций.

---

## 5. Verification Method (Метод независимой проверки)

### 5.1. Команды проверки
1. **Запуск базового набора тестов**:
   ```bash
   PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_working_slice.py
   ```
   *Ожидаемый результат:* 17 passed.
2. **Запуск нового набора тестов PATCH**:
   ```bash
   PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_interaction_patch.py
   ```
   *Ожидаемый результат:* Все тесты завершаются со статусом PASSED (100% OK).
3. **Запуск полного тестового набора**:
   ```bash
   PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/
   ```
4. **Проверка инвариантов бизнес-процесса и отчётов**:
   ```bash
   backend/.venv/bin/python docs/checks/verify_workflow.py
   backend/.venv/bin/python docs/checks/verify_reports.py
   backend/.venv/bin/python docs/checks/verify_plan.py
   ```
   *Ожидаемый результат:* Все три скрипта выводят PASS.

### 5.2. Условия инвалидации (Invalidation Conditions)
Любое из следующих событий означает нарушение требований:
- Возврат кода 403 вместо 404 при попытке менеджера Б обратиться к чужой карточке менеджера А (нарушение 152-ФЗ / AC06).
- Возврат кода 200 при несовпадении `expected_revision` (нарушение CAS / AC01).
- Успешный переход в `materials_transfer` для карточки с пустыми `program_id`/`product_id` (нарушение инварианта графа workflow).
- Дублирование событий `attributes_corrected` при повторном запросе с тем же `Idempotency-Key` (нарушение идемпотентности).
- Падение любого из 17 существующих тестов `test_working_slice.py`.
