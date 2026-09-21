# Спецификационный отчёт: Задачи B11, B14, B15, B18 (Пакет R1, R2, R3, R4, R5)

**Рабочая директория:** `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_survey_1`  
**Дата фиксации:** 2026-09-19  
**Роль:** Specification Miner (`teamwork_preview_spec_miner`)  
**Основание:** `ORIGINAL_REQUEST.md`, `AGENTS.md`, `ADR 001`, `ADR 002`, `01-technical-specification.md`, `02-development-plan.md`, `03-acceptance-scenarios.md`, `04-base-workflow.json`, `05-report-fixture.json`.

---

## 1. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| F01 | Data Model (B11) | Сущность `OrganizationContact` | Контакты вузов / ответственные лица от организации | `organization_id` (FK), `full_name` (str 250), `position` (str 200), `email` (str 200 nullable), `phone` (str 100 nullable), `active` (bool def True) | Созданный контакт с UUID | 422 при превышении длины или отсутствии обязательных полей | `ORIGINAL_REQUEST.md:30`, `ADR-002:28-36`, `01-tech-spec:68` |
| F02 | Data Model (B11) | Сущность `Contract` | Договоры с образовательными организациями | `organization_id` (FK), `number` (str 100), `signed_on` (DateTime tz nullable), `status` (str 50 def "active") | Созданный договор с UUID и `created_at` | 422 при невалидных типах/длине | `ORIGINAL_REQUEST.md:31`, `ADR-002:37-44`, `01-tech-spec:102` |
| F03 | Data Model (B11) | Сущность `License` | Лицензии на ПО, переданные организации | `organization_id` (FK), `product_id` (FK), `contract_id` (FK nullable), `signed_on` (DateTime tz nullable), `term_years` (int nullable), `transfer_status` (str 50 def "pending") | Созданная запись лицензии | 422 при нарушении FK или невалидных полях | `ORIGINAL_REQUEST.md:32`, `ADR-002:45-54`, `01-tech-spec:103` |
| F04 | Data Model (B11) | Расширение `Interaction` внешними ключами | Добавление связей с контактом, договором и лицензией | `contract_id` (FK contracts.id, nullable), `license_id` (FK licenses.id, nullable), `contact_id` (FK organization_contacts.id, nullable) | Обновленный объект `Interaction` | 422/FK Integrity Error при ссылке на несуществующую сущность | `ORIGINAL_REQUEST.md:34`, `ADR-002:67-72` |
| F05 | API & Catalogs (B11) | Сериализация договоров, лицензий и контактов в каталогах | Включение новых сущностей в ответ `/api/v1/catalogs` для доступных организаций | `db: Session`, `user: User` | JSON с массивами `contacts`, `contracts`, `licenses` в рамках видимых организаций пользователя | 401 UNAUTHENTICATED при отсутствии сессии | `ORIGINAL_REQUEST.md:35`, `ADR-002:2.1`, `services.py:catalogs` |
| F06 | API & Detail (B11) | Сериализация связанных полей карточки взаимодействия | Добавление информации о контакте, договоре и лицензии в `interaction_dict` | `item: Interaction` | Поля `contact_id`, `contact_name`, `contract_id`, `contract_number`, `license_id`, `license_status` | Безопасные `None` при отсутствии связей | `ORIGINAL_REQUEST.md:36`, `ADR-002:2.1`, `services.py:interaction_dict` |
| F07 | Data Model & Storage (B18) | Сущность `Attachment` | Вложения 10 форматов ТЗ с SHA-256 хешированием | `interaction_id` (FK), `visit_id` (str), `file_name` (255), `file_path` (500), `file_size` (int <= 25MB), `content_type` (100), `checksum` (64 sha256), `uploaded_by` (FK users) | Запись метаданных файла | 413 FILE_TOO_LARGE (>25MB), 422 INVALID_FILE_TYPE (не из списка 10 расширений) | `ORIGINAL_REQUEST.md:33`, `ADR-002:55-66`, `01-tech-spec:105` |
| F08 | API Endpoint (B14, B15) | Маршрут `PATCH /api/v1/interactions/{id}` | Частичное обновление атрибутов карточки с защитой от дедлока D02 | `InteractionUpdate` body, заголовок `Idempotency-Key` (до 200 символов) | Обновленный `interaction_dict` с `revision = expected_revision + 1` | 404 NOT_FOUND (чужая/несуществующая), 409 REVISION_CONFLICT, 409 IDEMPOTENCY_CONFLICT, 422 VALIDATION_ERROR | `ORIGINAL_REQUEST.md:39-47`, `ADR-002:73-96`, `01-tech-spec:275` |
| F09 | Concurrency (B14) | Атомарный CAS update по `expected_revision` | Гарантия отсутствия перезаписи чужих правок при конкурентной работе | `expected_revision: int` в теле `InteractionUpdate` | Инкремент `revision = revision + 1` при точном совпадении | 409 Conflict с кодом `REVISION_CONFLICT` при несовпадении ревизии | `ORIGINAL_REQUEST.md:43`, `AGENTS.md:2.2`, `ADR-002:93` |
| F10 | Workflow Fix (B14, B15) | Устранение дедлока D02 | Дозаполнение программы и продукта в карточку, созданную без них, для разблокировки перехода в `materials_transfer` | `program_id`, `product_id` в `PATCH` | Карточка получает связанные программу и продукт | 422 при несовместимости программы и продукта | `ORIGINAL_REQUEST.md:44, 68`, `ADR-002:17-18`, `07-gap-analysis:111-115` |
| F11 | Business Rules (B14) | Инвариант поздних этапов (Late-Stage Subject Protection) | Запрет обнуления программы и продукта на этапе `materials_transfer` и последующих | Попытка передать `null` для `program_id` или `product_id`, когда `state in SUBJECT_REQUIRED_STATES` | Отклонение запроса | 422 VALIDATION_ERROR («Нельзя сбросить программу или продукт на текущем этапе») | `ORIGINAL_REQUEST.md:45`, `01-tech-spec:141` |
| F12 | Audit Trail (B14) | Темпоральное событие `attributes_corrected` | Фиксация факта и состава изменений параметров карточки в аудит-логе | Атрибуты до и после изменения | Запись `InteractionEvent(type="attributes_corrected", sequence=last+1, payload={"changes": {...}, "snapshot": ...})` | 500 / rollback при сбое фиксации события | `ORIGINAL_REQUEST.md:46`, `ADR-002:94`, `01-tech-spec:113` |
| F13 | UI Design System (R3) | CSS-токены Rostelecom Light Theme | Внедрение утвержденных брендовых цветов и скруглений Gen2 Atomaro | Переменные CSS в `:root`: `--rtk-color-primary: #7700FF`, `--rtk-color-accent: #FF4F12`, `--rtk-color-background: #F4F5F8`, `--rtk-color-card: #FFFFFF`, `--rtk-color-border: #E2E5EB`, `--rtk-color-text: #101828`, `--rtk-color-muted: #475467`, `--rtk-radius-md: 8px`, `--rtk-radius-lg: 12px` | Применение стилей ко всем кнопкам, карточкам, хедерам, таблицам | Нарушение палитры предотвращается запретом хардкода | `ORIGINAL_REQUEST.md:49-55`, `ADR-001:26-32`, `08-ui-design-analysis:31-47` |
| F14 | UI Workflow (B15, R3) | Отображение всех доступных переходов в карточке | Устранение хардкода `allowed_transitions[0]` и отрисовка кнопок для всех путей | Массив `item.allowed_transitions` | Набор кнопок: `primary` (прямой переход), `secondary` (доработка/цикл), `danger` (отмена) | Блокировка кнопки и валидация комментария при `comment_required == true` | `ORIGINAL_REQUEST.md:56-60`, `ADR-002:98-101`, `07-gap-analysis:116-120` |
| F15 | UI Modal & Form (R3) | Модальное окно «Редактировать параметры» | Интерактивная форма правки программы, продукта, метки цикла, контакта и договора | Выбор совместимых программ, продуктов, контактов и договоров вуза | Отправка `PATCH` запроса с `crypto.randomUUID()` в `Idempotency-Key` и реактивное обновление карточки | 409 Conflict выводится информативным алертом без сброса формы | `ORIGINAL_REQUEST.md:61-65`, `AGENTS.md:4.2` |
| F16 | Security & Scope (R4) | Изоляция доступа по 152-ФЗ | Защита от прямого доступа к чужим взаимодействиям через `PATCH`, `GET`, `transitions` | Запрос от неавторизованного пользователя или менеджера чужой карточки | Строгий ответ 404 Not Found (не раскрывать факт существования) | 404 NOT_FOUND | `ORIGINAL_REQUEST.md:72, 99`, `AGENTS.md:3.1`, `01-tech-spec:168` |

---

## 2. Edge Cases

| # | Feature | Input | Observed / Specified Behavior |
|---|---------|-------|-------------------------------|
| E01 | `PATCH /interactions/{id}` | Отсутствует заголовок `Idempotency-Key` или он состоит только из пробелов | Ошибка `422 VALIDATION_ERROR`: «Нужен непустой заголовок Idempotency-Key (до 200 символов)». Изменения не вносятся. |
| E02 | `PATCH /interactions/{id}` | Заголовок `Idempotency-Key` длиннее 200 символов | Ошибка `422 VALIDATION_ERROR`: «Нужен непустой заголовок Idempotency-Key (до 200 символов)». |
| E03 | `PATCH /interactions/{id}` | Повторный запрос с тем же `Idempotency-Key` и идентичным телом | Идемпотентный возврат `200 OK` с ранее сохраненным ответом. Новое событие `attributes_corrected` НЕ создается. |
| E04 | `PATCH /interactions/{id}` | Повторный запрос с тем же `Idempotency-Key`, но с измененным телом | Ошибка `409 IDEMPOTENCY_CONFLICT`: «Этот ключ уже использован с другим содержимым.». Транзакция откатывается. |
| E05 | `PATCH /interactions/{id}` | `expected_revision` не равен текущей `revision` карточки (устаревшая ревизия) | Ошибка `409 REVISION_CONFLICT`: «Карточка изменена. Обновите данные.». CAS `update ... where revision == expected_revision` затрагивает 0 строк, транзакция откатывается. |
| E06 | `PATCH /interactions/{id}` | Запрос к карточке другого менеджера (`Interaction.owner_id != user.id` и нет прав руководителя) | Ответ `404 NOT_FOUND`: «Взаимодействие не найдено.». Факт существования карточки скрывается в соответствии с 152-ФЗ. |
| E07 | `PATCH /interactions/{id}` | Передача неизвестного `program_id` или `product_id` | Ошибка `422 VALIDATION_ERROR`: «Неизвестная ИТ-программа.» или «Неизвестный ИТ-продукт.». |
| E08 | `PATCH /interactions/{id}` | Передача пары `program_id` и `product_id`, отсутствующей в таблице `ProgramProduct` | Ошибка `422 VALIDATION_ERROR`: «Продукт не связан с выбранной программой.». |
| E09 | `PATCH /interactions/{id}` | Попытка передать `program_id = null` или `product_id = null`, когда карточка уже в статусе `materials_transfer`, `deployment`, `teacher_training`, `curriculum_update`, `classes`, `materials_update`, `teacher_upskilling` или `completed` | Ошибка `422 VALIDATION_ERROR`: «Нельзя сбросить программу или продукт на текущем этапе.». |
| E10 | `PATCH /interactions/{id}` | Передача `contact_id`, `contract_id` или `license_id`, принадлежащих ДРУГОЙ организации (`organization_id != item.organization_id`) | Ошибка `422 VALIDATION_ERROR`: сущность принадлежит другой образовательной организации. |
| E11 | `PATCH /interactions/{id}` | Карточка находится в терминальном состоянии (`completed` или `cancelled`, `closed_at != None`) | Ошибка `422 VALIDATION_ERROR`: завершенные взаимодействия не подлежат редактированию. |
| E12 | `PATCH /interactions/{id}` | Тело запроса содержит запрещенные поля (например `organization_id`, `owner_id`, `state`) | Ошибка `422 RequestValidationError`: Pydantic схема с `extra="forbid"` немедленно отклоняет запрос. |
| E13 | UI Transition Actions | Карточка на этапе `document_signing` без программы/продукта | При попытке нажать «Перевести на следующий этап» сервер возвращает 422: «Перед этим этапом укажите ИТ-программу и ИТ-продукт.». Пользователь открывает модальное окно «Редактировать параметры», указывает программу и продукт, отправляет PATCH, после чего кнопка перехода срабатывает успешно (разрешение дедлока D02). |
| E14 | UI Transition Actions | Переход с `comment_required: true` (например, `document_signing_to_document_revision` или отмена) | Интерфейс открывает модальное окно/поле комментария, блокирует кнопку отправки при пустом комментарии, проверяет `comment.trim().length > 0`. |
| E15 | UI Transition Actions | Карточка в терминальном состоянии (`completed` или `cancelled`) | Массив `allowed_transitions` пуст (`[]`). Интерфейс скрывает блок действий и выводит баннер «Карточка завершена. Новых переходов нет.». |
| E16 | Attachment Upload | Загрузка файла с недопустимым расширением (например `.exe`, `.sh`, `.bat`) | Отклонение запроса с кодом `422 VALIDATION_ERROR`. Разрешены только 10 форматов ТЗ: `png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx`. |
| E17 | Attachment Upload | Загрузка файла размером более 25 МБ (26 214 400 байт) | Отклонение запроса с кодом `413 FILE_TOO_LARGE`. |
| E18 | Reassignment Access Revocation | Руководитель переназначает карточку от Менеджера А к Менеджеру Б | Менеджер А немедленно теряет доступ (`GET` и `PATCH` возвращают 404). Менеджер Б получает доступ. В исторических отчетах на дату создания карточки владельцем остается Менеджер А. |

---

## 3. Точные контракты данных и схемы (Data Contracts & Schemas)

### 3.1. Модели SQLAlchemy (`backend/app/models.py`)

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
    status: Mapped[str] = mapped_column(String(50), default="active")  # 'active', 'draft', 'expired', 'terminated'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class License(Base):
    __tablename__ = "licenses"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    signed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    term_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transfer_status: Mapped[str] = mapped_column(String(50), default="pending")  # 'pending', 'transferred', 'active'
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
    checksum: Mapped[str] = mapped_column(String(64))  # sha256
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

**Расширение `Interaction`:**
```python
contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
license_id: Mapped[str | None] = mapped_column(ForeignKey("licenses.id"), nullable=True)
contact_id: Mapped[str | None] = mapped_column(ForeignKey("organization_contacts.id"), nullable=True)
```

### 3.2. Pydantic-схема `InteractionUpdate` (`backend/app/schemas.py`)

```python
class InteractionUpdate(Body):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=250)
    program_id: str | None = None
    product_id: str | None = None
    cycle_label: str | None = Field(default=None, min_length=1, max_length=100)
    contract_id: str | None = Field(default=None, max_length=64)
    license_id: str | None = Field(default=None, max_length=64)
    contact_id: str | None = Field(default=None, max_length=64)
```

### 3.3. Сериализация в `interaction_dict` (`backend/app/services.py`)

```python
contact = db.get(OrganizationContact, item.contact_id) if getattr(item, "contact_id", None) else None
contract = db.get(Contract, item.contract_id) if getattr(item, "contract_id", None) else None
license_obj = db.get(License, item.license_id) if getattr(item, "license_id", None) else None

# Дополнить результирующий словарь полями:
"contact_id": item.contact_id,
"contact_name": contact.full_name if contact else None,
"contract_id": item.contract_id,
"contract_number": contract.number if contract else None,
"license_id": item.license_id,
"license_status": license_obj.transfer_status if license_obj else None,
```

### 3.4. Каталоги `/api/v1/catalogs`

Ответ дополняется ключами:
```json
{
  "organizations": [...],
  "programs": [...],
  "products": [...],
  "owners": [...],
  "directions": [...],
  "contacts": [
    {
      "id": "contact-uuid",
      "organization_id": "org-1",
      "full_name": "Иванов Иван Иванович",
      "position": "Декан ИТ факультета",
      "email": "ivanov@univ.ru",
      "phone": "+7 (999) 000-00-00",
      "active": true
    }
  ],
  "contracts": [
    {
      "id": "contract-uuid",
      "organization_id": "org-1",
      "number": "Д-2026/01",
      "signed_on": "2026-03-01T00:00:00Z",
      "status": "active"
    }
  ],
  "licenses": [
    {
      "id": "license-uuid",
      "organization_id": "org-1",
      "product_id": "product-cloud",
      "contract_id": "contract-uuid",
      "signed_on": "2026-03-05T00:00:00Z",
      "term_years": 1,
      "transfer_status": "transferred"
    }
  ]
}
```

---

## 4. Статусы и семантика переходов Workflow (15 состояний, 29 переходов)

### 4.1. Состояния жизненного цикла

1. `contact_search` (Поиск контактов, начальный, source_step 1)
2. `needs_clarification` (Уточнение потребности, source_step 2)
3. `meeting` (Встреча с вузом, source_step 3)
4. `document_exchange` (Обмен документами, source_step 4)
5. `document_revision` (Корректировка документов, опциональный, source_step 5)
6. `document_signing` (Подписание документов, source_step 6)
7. `materials_transfer` (Передача материалов и лицензии, source_step 7, **требует program_id и product_id**)
8. `deployment` (Сопровождение внедрения, source_step 8)
9. `teacher_training` (Обучение преподавателей, source_step 9)
10. `curriculum_update` (Актуализация учебной программы, source_step 10)
11. `classes` (Ведение занятий, source_step 11)
12. `materials_update` (Актуализация материалов, source_step 12)
13. `teacher_upskilling` (Повышение квалификации преподавателей, source_step 13)
14. `completed` (Взаимодействие завершено, терминальный, kind: terminal, outcome: completed)
15. `cancelled` (Взаимодействие отменено, терминальный, kind: terminal, outcome: cancelled)

**Сквозной контроль:** Пункт 14 ТЗ («Контроль за исполнением каждого этапа») реализован как сквозная функция отображения истории переходов, ответственных и посещений, без отдельного состояния.

### 4.2. Классификация переходов и варианты кнопок UI

| Тип перехода (`kind`) | `comment_required` | Вариант кнопки UI | Пример ребра |
|---|---|---|---|
| `forward` (основной шаг) | `false` | `variant="primary"` | `document_signing_to_materials_transfer` |
| `skip_optional` (пропуск) | `false` | `variant="primary"` | `document_exchange_to_document_signing` |
| `rework` (возврат на доработку) | `true` | `variant="secondary"` | `document_signing_to_document_revision` |
| `cycle` (повторный цикл) | `true` | `variant="secondary"` | `teacher_upskilling_to_classes` |
| `cancellation` (отмена) | `true` | `variant="danger"` | `<state>_to_cancelled` (13 переходов) |

---

## 5. Формат ошибок и матрица HTTP-статусов

Все ошибки API строго следуют стандарту:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Человекочитаемое сообщение на русском языке.",
    "request_id": "uuid-v4-запроса",
    "details": null
  }
}
```

| HTTP Статус | Код ошибки (`error.code`) | Сценарий возникновения |
|---|---|---|
| `401 Unauthorized` | `UNAUTHENTICATED` | Не передан `X-Demo-User` (в demo) или отсутствующий/невалидный JWT Bearer (в oidc) |
| `403 Forbidden` | `FORBIDDEN` | Попытка выполнить действие без прав (например, назначить чужого менеджера, создать карточку чужой организации) |
| `404 Not Found` | `NOT_FOUND` | Обращение к чужой карточке менеджером (152-ФЗ) либо обращение к несуществующей карточке / организации |
| `409 Conflict` | `REVISION_CONFLICT` | Несовпадение `expected_revision` с текущей `Interaction.revision` (CAS конфликт) |
| `409 Conflict` | `IDEMPOTENCY_CONFLICT` | Тот же `Idempotency-Key` передан с другим телом запроса |
| `409 Conflict` | `TRANSITION_NOT_ALLOWED` | Переход недоступен из текущего состояния процесса |
| `413 Payload Too Large` | `FILE_TOO_LARGE` | Загрузка файла размером более 25 МБ |
| `422 Unprocessable` | `VALIDATION_ERROR` | Несовместимые программа/продукт, сброс программы на позднем этапе, пустой `Idempotency-Key`, пустой обязательный комментарий |

---

## 6. Handoff Report (5-Component Protocol)

### 6.1. Observation
1. **Отсутствие моделей:** В файле `backend/app/models.py` (строки 1–128) определены только `User`, `Organization`, `OrganizationAccess`, `Direction`, `Program`, `Product`, `ProgramProduct`, `Interaction`, `InteractionEvent`, `Comment`, `CommandResult`. Классы `OrganizationContact`, `Contract`, `License`, `Attachment` отсутствуют.
2. **Дефицит полей в `Interaction`:** В `models.py:70-87` модель `Interaction` не содержит внешних ключей `contract_id`, `license_id`, `contact_id`.
3. **Отсутствие эндпоинта PATCH:** В `backend/app/main.py:126-184` присутствуют методы `GET /interactions`, `GET /interactions/{id}`, `POST /interactions`, `POST /interactions/{id}/transitions`, `POST /interactions/{id}/comments`, `POST /interactions/{id}/assignments`. Метод `PATCH /api/v1/interactions/{id}` не реализован.
4. **Ограничение выбора перехода в UI:** В `frontend/src/views/InteractionPage.tsx:29` жестко зафиксировано: `const transition = item.allowed_transitions[0];`. Альтернативные ветви (`rework`, `cancellation`, `cycle`) скрыты от пользователя.
5. **Отсутствие UI редактирования параметров:** В `InteractionPage.tsx` отсутствует модальное окно или форма вызова обновления программы, продукта, цикла, договора или контакта.
6. **Цветовая палитра:** В `frontend/src/styles.css:1` цвета заданы старыми значениями (`#6c53bf`, `#20183e`, `#f36e39`) без CSS-переменных токенов Ростелеком Gen2 (`--rtk-color-primary: #7700FF`, `--rtk-color-accent: #FF4F12`, `--rtk-color-background: #F4F5F8`, `--rtk-color-text: #101828`).
7. **Текущий статус тестов:**
   - Команда `PYTHONPATH=. ./.venv/bin/pytest` в директории `backend/` успешно выполнила все 17 тестов в `tests/test_working_slice.py` (`17 passed in 3.46s`).
   - Скрипты проверки графа и спецификаций `docs/checks/verify_workflow.py`, `docs/checks/verify_reports.py`, `docs/checks/verify_plan.py` завершились успешно с выводом `PASS`.

### 6.2. Logic Chain
1. *Из наблюдения 1 и 2* следует, что требования R1 (задачи B11, B18) и предписания ADR 002 не выполнены в текущем срезе: в БД нет сущностей договоров, лицензий, контактов и вложений.
2. *Из наблюдения 3* в связке с правилом D02 (`workflow.py:9-12: SUBJECT_REQUIRED_STATES = {"materials_transfer", ...}`) следует наличие критического дедлока D02: если карточка создана без программы и продукта (что легитимно на этапе `contact_search`), ее невозможно перевести в статус `materials_transfer` без эндпоинта `PATCH /api/v1/interactions/{id}`.
3. *Из наблюдения 4* следует, что требование R3 и сценарии AC07, AC09 нарушены в пользовательском интерфейсе: менеджер не может отменить взаимодействие или отправить документы на доработку, так как интерфейс принудительно отображает только первый элемент массива `allowed_transitions`.
4. *Из наблюдения 5 и 6* следует, что дизайн-система Ростелеком Gen2 (ADR 001) не внедрена, а кнопка «Редактировать параметры» отсутствует, что делает невозможным интерактивное устранение дедлока пользователем в браузере.
5. *Из наблюдения 7* следует, что существующая база тестов стабильна и все новые доработки (B11, B14, B15, B18) должны сохранять 100% обратную совместимость с `test_working_slice.py`.

### 6.3. Caveats
- Распаковка архивов (ZIP, RAR, GZIP) при загрузке вложений не требуется по ТЗ и запрещена проектным решением D16 (только хранение метаданных, проверка контрольной суммы и безопасная выдача).
- Эндпоинт `PATCH /api/v1/interactions/{id}` не должен позволять изменять `organization_id` или `owner_id` (смена ответственного выполняется строго через `POST /interactions/{id}/assignments`, а смена организации существующей карточки запрещена спецификацией D05).
- Фронтенд-сборка `pnpm build` требует предварительной установки зависимостей или запуска в подготовленном контейнере.

### 6.4. Conclusion
Пакет требований для реализации задач B11, B14, B15, B18 полностью специфицирован и готов к непосредственной передаче инженерам разработки (Backend, Frontend, QA):
1. **Backend Engineer:** создать модели `OrganizationContact`, `Contract`, `License`, `Attachment`; расширить `Interaction`; реализовать схему `InteractionUpdate`; реализовать маршрут `PATCH /api/v1/interactions/{id}` с CAS-блокировкой, идемпотентностью и темпоральным событием `attributes_corrected`; обновить `catalogs` и `interaction_dict`; добавить сиды в `seed.py`.
2. **Frontend & UX Engineer:** внедрить CSS-токены темы Rostelecom Light (`--rtk-*`) в `styles.css`; переписать блок действий в `InteractionPage.tsx` для отображения всех переходов с цветовой дифференциацией; разработать модальное окно «Редактировать параметры» с отправкой `PATCH` и реактивным обновлением SPA.
3. **QA & Test Engineer:** разработать тестовый модуль `backend/tests/test_interaction_patch.py`, покрывающий устранение дедлока D02, CAS-конфликты, валидацию связей, идемпотентность и изоляцию доступа (152-ФЗ); проконтролировать прохождение 100% тестов `test_working_slice.py`.

### 6.5. Verification Method
1. **Проверка тестов бэкенда:**
   ```bash
   cd /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend
   PYTHONPATH=. ./.venv/bin/pytest tests/test_working_slice.py tests/test_interaction_patch.py
   ```
   *Критерий успеха:* 100% тестов завершаются со статусом `passed`.
2. **Проверка системных чекеров:**
   ```bash
   cd /home/muhammad/Dev/HACKATHON/LCT/rost_crm
   python3 docs/checks/verify_workflow.py
   python3 docs/checks/verify_reports.py
   python3 docs/checks/verify_plan.py
   ```
   *Критерий успеха:* Все скрипты возвращают `PASS`.
3. **Инспекция файлов:**
   - `backend/app/models.py` содержит классы `OrganizationContact`, `Contract`, `License`, `Attachment`.
   - `backend/app/main.py` содержит обработчик `@app.patch("/api/v1/interactions/{interaction_id}")`.
   - `frontend/src/styles.css` содержит переменные `--rtk-color-primary: #7700FF`, `--rtk-color-accent: #FF4F12`.
   - `frontend/src/views/InteractionPage.tsx` рендерит `item.allowed_transitions.map(...)`.
