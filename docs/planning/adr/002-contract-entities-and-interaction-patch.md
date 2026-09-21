# ADR 002: Схема договоров, лицензий, контактов и метод PATCH /interactions/{id}

**Статус:** Принято к исполнению  
**Дата:** 19 сентября 2026 года  
**Автор:** Технический архитектор проекта rost_crm  
**Связанные задачи:** B11, B14, B15, B18  
**Связанные сценарии приёмки:** AC01, AC06, AC07, AC09, AC10  

---

## 1. Контекст и проблема

1. **Дефицит сущностей ТЗ (стр. 4 исходного ТЗ):**
   В ТЗ прямо указаны обязательные поля каталогов и карточек: «Номер договора», «Подписание лицензии», «Срок действия лицензии (год)», «Статус по передаче», «Ответственные от ВУЗа», «Вендор», «ПО».
   В текущей модели `models.py` эти поля отсутствовали.
2. **Блокировка жизненного цикла (Deadlock Workflow):**
   Правило `D02` и код `SUBJECT_REQUIRED_STATES` в `backend/app/workflow.py` запрещают перевод карточки в статус `materials_transfer` и далее, если не выбраны `program_id` и `product_id`. Карточка может создаваться без них (на этапе первичного контакта программа/продукт еще неизвестны).
   Без эндпоинта редактирования карточки (`PATCH /api/v1/interactions/{id}`) карточка без программы/продукта блокируется на этапе `document_signing`.
3. **Ограничение UI переходов:**
   В `InteractionPage.tsx` захардкожен только первый переход `allowed_transitions[0]`, из-за чего скрыты альтернативные пути (отмена, доработка).

---

## 2. Архитектурное решение

### 2.1. Новые модели данных в `backend/app/models.py`

1. **`OrganizationContact` (Ответственные лица от вуза):**
   - `id`: `String(64)`, primary_key, default `new_id`
   - `organization_id`: `ForeignKey("organizations.id")`, index=True
   - `full_name`: `String(250)` (ФИО ответственного от вуза)
   - `position`: `String(200)` (Должность, например «Декан факультета ИТ»)
   - `email`: `String(200)`, nullable=True
   - `phone`: `String(100)`, nullable=True
   - `active`: `Boolean`, default True

2. **`Contract` (Договоры с организациями):**
   - `id`: `String(64)`, primary_key, default `new_id`
   - `organization_id`: `ForeignKey("organizations.id")`, index=True
   - `number`: `String(100)` (Номер договора)
   - `signed_on`: `DateTime(timezone=True)`, nullable=True (Дата подписания)
   - `status`: `String(50)`, default "active"
   - `created_at`: `DateTime(timezone=True)`, default `utcnow`

3. **`License` (Лицензии на ПО):**
   - `id`: `String(64)`, primary_key, default `new_id`
   - `organization_id`: `ForeignKey("organizations.id")`, index=True
   - `product_id`: `ForeignKey("products.id")`, index=True
   - `contract_id`: `ForeignKey("contracts.id")`, nullable=True
   - `signed_on`: `DateTime(timezone=True)`, nullable=True (Подписание лицензии)
   - `term_years`: `Integer`, nullable=True (Срок действия лицензии в годах)
   - `transfer_status`: `String(50)`, default "pending" (Статус по передаче)
   - `created_at`: `DateTime(timezone=True)`, default `utcnow`

4. **`Attachment` (Вложения файлов 10 форматов):**
   - `id`: `String(64)`, primary_key, default `new_id`
   - `interaction_id`: `ForeignKey("interactions.id")`, index=True
   - `visit_id`: `String(64)`, index=True (Привязка к этапу/посещению)
   - `file_name`: `String(255)` (Оригинальное имя файла)
   - `file_path`: `String(500)` (Путь в изолированном хранилище)
   - `file_size`: `Integer` (Размер в байтах, до 25 МБ)
   - `content_type`: `String(100)` (MIME-тип)
   - `checksum`: `String(64)` (SHA-256 хеш)
   - `uploaded_by`: `ForeignKey("users.id")`
   - `created_at`: `DateTime(timezone=True)`, default `utcnow`

5. **Расширение `Interaction`:**
   - Добавить внешние ключи:
     - `contract_id`: `ForeignKey("contracts.id")`, nullable=True
     - `license_id`: `ForeignKey("licenses.id")`, nullable=True
     - `contact_id`: `ForeignKey("organization_contacts.id")`, nullable=True

### 2.2. Новый эндпоинт `PATCH /api/v1/interactions/{id}`

- **Аутентификация и права:** Требуется разрешение `interactions.edit` (доступно `manager` для своих карточек и `supervisor` для своей команды).
- **Заголовки:** Обязателен `Idempotency-Key` (до 200 символов).
- **Тело запроса (`InteractionUpdate`):**
  ```json
  {
    "expected_revision": 1,
    "title": "Новое название (опционально)",
    "program_id": "program-qa (опционально)",
    "product_id": "product-test (опционально)",
    "cycle_label": "Осень 2026 (опционально)",
    "contract_id": "contract-uuid (опционально)",
    "license_id": "license-uuid (опционально)",
    "contact_id": "contact-uuid (опционально)"
  }
  ```
- **Логика:**
  1. Проверка `scope_clause(user)` (чужой ID -> `404 Not Found`).
  2. Валидация сочетаемости `program_id` и `product_id` через `validate_subject(db, program_id, product_id)`.
  3. Атомарный CAS update по `expected_revision`.
  4. Создание темпорального события `InteractionEvent(type="attributes_corrected")` с фиксацией изменений.
  5. Возврат обновленного `Interaction` с инкрементированным `revision`.

### 2.3. Доработка UI переходов в `InteractionPage.tsx`
- Выводить все доступные переходы из массива `allowed_transitions`:
  - Основной следующий переход (кнопка `Button variant="primary"`).
  - Альтернативные переходы (возврат на доработку `Button variant="secondary"`, отмена `Button variant="danger"`).
- Если у выбранного перехода `comment_required == true`, открывать модальное окно ввода комментария с валидацией непустой строки.
