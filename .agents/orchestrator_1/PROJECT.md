# Project: rost_crm — Задачи B11, B14, B15, B18 (R1–R5)

## Architecture
- **Backend Architecture**: FastAPI, SQLAlchemy 2.0 (declarative mapping, SQLite engine with foreign keys enabled, Base.metadata.create_all), Pydantic v2 schemas.
- **Workflow Engine**: 13 working states + 2 terminal states (completed, cancelled), 29 transitions, strict validation of subject (`SUBJECT_REQUIRED_STATES` from `materials_transfer` onwards).
- **Concurrency & Idempotency**:
  - CAS update via `Interaction.revision == expected_revision` (returning 409 `REVISION_CONFLICT` on mismatch).
  - Idempotent commands via `CommandResult` keyed by `(user_id, operation, idempotency_key)` with SHA-256 payload digest.
- **Security & Access Control (152-ФЗ, ФСТЭК №117)**:
  - Scoped queries via `scoped_interaction(db, user, id)` returning strict 404 Not Found on access violation.
  - In-memory JWT tokens (no `localStorage` / `sessionStorage`).
- **Frontend Architecture**:
  - React SPA with custom lightweight UI components (`Button`, `Modal`, `ErrorAlert`, `Icon`, `Avatar`).
  - Rostelecom Gen2 Light Theme tokens in CSS (`--rtk-color-primary: #7700FF`, `--rtk-color-accent: #FF4F12`, `--rtk-color-background: #F4F5F8`, `--rtk-color-text: #101828`).
  - Native browser APIs: `crypto.randomUUID()`, native date/file inputs. Zero unneeded dependencies.

---

## Feature Inventory
| # | Feature | Description | Milestone | Status |
|---|---------|-------------|-----------|--------|
| 1 | F01: OrganizationContact | Модель `OrganizationContact` (контакты вузов) | M1: Backend | DONE |
| 2 | F02: Contract | Модель `Contract` (договоры сотрудничества) | M1: Backend | DONE |
| 3 | F03: License | Модель `License` (лицензии на ПО) | M1: Backend | DONE |
| 4 | F04: Attachment | Модель `Attachment` (метаданные файлов 10 форматов, sha256) | M1: Backend | DONE |
| 5 | F05: Interaction FKs | Расширение `Interaction` внешними ключами `contract_id`, `license_id`, `contact_id` | M1: Backend | DONE |
| 6 | F06: Catalogs & Detail Enrichment | Сериализация контактов, договоров и лицензий в `catalogs()` и связанных полей в `interaction_dict()` | M1: Backend | DONE |
| 7 | F07: Seed Data | Демо-данные контактов, договоров и лицензий с сохранением инварианта `read_all=False` | M1: Backend | DONE |
| 8 | F08: InteractionUpdate Schema | Pydantic v2 схема `InteractionUpdate` с `expected_revision` | M1: Backend | DONE |
| 9 | F09: PATCH /interactions/{id} | Эндпоинт частичного обновления параметров с CAS и `Idempotency-Key` (до 200 симв.) | M1: Backend | DONE |
| 10 | F10: Deadlock D02 Resolution | Устранение дедлока D02: дозаполнение программы и продукта разблокирует `materials_transfer` | M1: Backend | DONE |
| 11 | F11: Late-Stage Subject Protection | Запрет сброса программы и продукта на этапах `materials_transfer` и далее (422) | M1: Backend | DONE |
| 12 | F12: Temporal Event attributes_corrected | Фиксация события `attributes_corrected` с payload changes в `InteractionEvent` | M1: Backend | DONE |
| 13 | F13: Rostelecom Gen2 Light Theme | Внедрение CSS-токенов темы Ростелеком Gen2 Light Theme в `styles.css` | M2: Frontend | DONE |
| 14 | F14: Full Allowed Transitions UI | Отображение всех переходов из `allowed_transitions` (primary, secondary, danger) | M2: Frontend | DONE |
| 15 | F15: Comment Required Modal | Модальное окно обязательного комментария для переходов с `comment_required: true` | M2: Frontend | DONE |
| 16 | F16: Edit Parameters Modal | Модальное окно «Редактировать параметры» (программа, продукт, цикл, контакт, договор) | M2: Frontend | DONE |
| 17 | F17: Frontend PATCH & SPA Reactive | Вызов PATCH с `crypto.randomUUID()` и `expected_revision`, реактивное обновление, 409 alert | M2: Frontend | DONE |
| 18 | F18: Automated Tests Suite | `test_interaction_patch.py`: D02 resolution, CAS 409, 422 validation, Idempotency, 152-FZ 404 | M3: QA | DONE |
| 19 | F19: Working Slice Regression Zero | Прохождение 100% тестов `test_working_slice.py` | M3: QA | DONE |
| 20 | F20: Ponytail & Verification Scripts | Аудит чистоты кода (stdlib, no deps) и успешный прогон `verify_workflow/reports/plan.py` | M4: Architecture & Ponytail | DONE |
| 21 | F21: Forensic Integrity Audit | Проверка отсутствия читинга, хардкода тестов, фейковых заглушек | M4: Architecture & Ponytail | DONE |

---

## Milestones

| # | Name | Specialist Role | Scope | Dependencies | Status | Outputs |
|---|------|-----------------|-------|-------------|--------|---------|
| M1 | Backend Engineering | Backend Engineer (`worker_backend_1`) | F01–F12: Models, catalogs, seed, PATCH endpoint, CAS, Idempotency, event logging | None | DONE | `models.py`, `schemas.py`, `services.py`, `main.py`, `seed.py` |
| M2 | Frontend & UX Engineering | Frontend & UX Engineer (`worker_frontend_2`) | F13–F17: CSS tokens, full transitions UI, comment modal, edit parameters modal, PATCH API call | M1 | DONE | `styles.css`, `types.ts`, `api.ts`, `InteractionPage.tsx` |
| M3 | QA & Test Engineering | QA & Test Engineer (`worker_qa_1`) | F18–F19: `test_interaction_patch.py`, 100% pass on `test_working_slice.py` | M1 | DONE | `backend/tests/test_interaction_patch.py` (27/27 tests PASS) |
| M4 | Architecture & Ponytail Review + Audit | Reviewer (`reviewer_arch_1`) & Forensic Auditor (`auditor_forensic_1`) | F20–F21: Ponytail review, verify scripts, build check, forensic integrity audit | M1, M2, M3 | DONE | Verdicts: APPROVE + CLEAN |

---

## Interface Contracts

### Backend ↔ Frontend Contract: `PATCH /api/v1/interactions/{id}`
- **Method & URL**: `PATCH /api/v1/interactions/{id}`
- **Headers**:
  - `Authorization: Bearer <token>` (or `X-Demo-User: <username>` in demo mode)
  - `Idempotency-Key: <UUID>` (string 1–200 characters, e.g. `crypto.randomUUID()`)
  - `Content-Type: application/json`
- **Request Body (`InteractionUpdate`)**:
  ```json
  {
    "expected_revision": 1,
    "title": "Новое название взаимодействия",
    "program_id": "program-devops",
    "product_id": "product-cloud",
    "cycle_label": "2026/2027",
    "contact_id": "contact-uuid-or-null",
    "contract_id": "contract-uuid-or-null",
    "license_id": "license-uuid-or-null"
  }
  ```
- **Response `200 OK`**:
  Updated `Interaction` dictionary with `revision: expected_revision + 1` and populated:
  - `contact_id`, `contact_name`
  - `contract_id`, `contract_number`
  - `license_id`, `license_status`
- **Error Codes**:
  - `404 Not Found` (`code: NOT_FOUND`): if interaction does not exist or user lacks scope (152-ФЗ).
  - `409 Conflict` (`code: REVISION_CONFLICT`): if `expected_revision != item.revision`.
  - `409 Conflict` (`code: IDEMPOTENCY_CONFLICT`): if key reused with different payload.
  - `422 Unprocessable` (`code: VALIDATION_ERROR`): incompatible program/product, reset subject in late state, or entity belongs to another organization.

### Backend Catalogs Contract: `GET /api/v1/catalogs`
- Extended response includes:
  - `contacts`: `[{ id, organization_id, full_name, position, email, phone, active }]`
  - `contracts`: `[{ id, organization_id, number, signed_on, status, created_at }]`
  - `licenses`: `[{ id, organization_id, product_id, contract_id, signed_on, term_years, transfer_status, created_at }]`

---

## Code Layout
- `backend/app/models.py`: SQLAlchemy models (`OrganizationContact`, `Contract`, `License`, `Attachment`, and `Interaction` FKs).
- `backend/app/schemas.py`: Pydantic schemas (`InteractionUpdate`, extended `InteractionCreate`).
- `backend/app/services.py`: Business logic (`permissions()`, `catalogs()`, `interaction_dict()`, `update_interaction()`, `event_dict()`).
- `backend/app/seed.py`: Demo seed data for contacts, contracts, licenses.
- `backend/app/main.py`: Route handler for `PATCH /api/v1/interactions/{interaction_id}`.
- `frontend/src/styles.css`: Rostelecom Gen2 Light Theme CSS variables and component styling.
- `frontend/src/types.ts`: TypeScript interfaces for contacts, contracts, licenses, update payload.
- `frontend/src/api.ts`: `ApiClient.patch` method.
- `frontend/src/views/InteractionPage.tsx`: Full `allowed_transitions` UI, comment modal, edit parameters modal.
- `backend/tests/test_interaction_patch.py`: Test suite for PATCH, CAS, D02 deadlock fix, scope isolation.
