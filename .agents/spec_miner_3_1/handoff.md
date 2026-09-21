# Handoff Report: Specification & Fixtures Miner (Resilient Integrations Contour)

**Author:** Specification & Fixtures Miner (`spec_miner_3_1`)  
**Target:** Orchestrator 3 (`orchestrator_3`), Backend Architect (`backend_builder_3`), Frontend & QA Engineer (`frontend_builder_3`)  
**Working Directory:** `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_3_1`  
**Date:** 2026-09-20T00:54:00Z  
**Scope:** Resilient Integrations Contour (Tasks B26, B27, B28, B29; Scenarios AC12, AC13, AC29, AC18, AC19; Requirements R09, R11, R12, R13, R20; Spec §7.2 DTO v1.0).

---

## 1. Observation

Directly observed facts and authoritative sources inspected:
1. **`docs/planning/01-technical-specification.md` (Section 7.2 «Внешние источники», Section 8 «API приложения»):**
   - Authoritative DTO v1.0 normalized envelope structure:
     `{"schema_version": "1.0", "source": "lms"|"website", "entity_type": "learning_metric"|"application", "external_id": "...", "source_revision": "...", "operation": "upsert"|"delete", "effective_at": "...", "received_at": "...", "payload": {...}}`.
   - Ingestion semantics: `received_at` is assigned by CRM at reception (`utcnow()`); `source_revision` is stored as string because external system ordering semantics cannot be compared lexicographically.
   - Dedup rules: Persistent match on `(source, entity_type, external_id)`; delivery deduplication key on `(source, entity_type, external_id, source_revision)`. Identical key + identical payload = duplicate (skip / idempotent replay); identical key + altered payload = conflict (`IDEMPOTENCY_CONFLICT`).
   - Domain field ownership: CRM owns assignments, permissions, stages, comments; LMS owns learning statistics; website owns applications / partner requests.
   - Unified error format:
     `{"error": {"code": "...", "message": "...", "request_id": "...", "details": {...}}}`.
2. **`docs/planning/02-development-plan.md` (Tasks B26–B29):**
   - **B26** (Common synchronization & reconciliation contour): Stores external IDs, cursors, event/receipt timestamps, processing audit logs; schema validation; deduplication, mid-stream failure handling, field ownership conflicts, and ambiguous entity mapping; creates new or amends existing interaction; pluggable contract mocks explicitly separated from live sources.
   - **B27** (LMS Zion connection): Zion LMS (`https://rtkb.zion-lms.ru/`), auth, pagination, metric reconciliation.
   - **B28** (Laravel website connection): Application ingestion, contacts, avoids naive name-only matching; conflict queue for manual reconciliation.
   - **B29** (Educational demand metrics): Cohorts, enrolled students, completed students, attendance rates by program and university; no arbitrary ungrounded scoring.
3. **`docs/planning/03-acceptance-scenarios.md` (AC12, AC13, AC18, AC19, AC29):**
   - **AC18** (Real integrations LMS and website): JSON ingestion, external IDs persisted, field ownership respected, ambiguous matching never merges records silently.
   - **AC19** (API duplicates, failure, payload conflicts): Dedup key prevents duplication; conflicting payload with same key returns diagnosable conflict; canonical event count stays invariant.
   - **AC29** (Archi, documentation, UI deliverable): Deliverable inspection, clear separation of mock and production environments.
4. **`AGENTS.md` & Security Invariants:**
   - Ponytail Ladder: 0 new external dependencies (use Python stdlib `hashlib`, `uuid`, `datetime`, `json`, `dataclasses`, and existing FastAPI/SQLAlchemy/Pydantic).
   - 152-FZ / FSTEK No. 117 Scope Isolation: Manager role cannot access global integration status, inbox, or trigger sync (`403 FORBIDDEN`). Supervisor and admin roles have access.
   - CAS revision protection and `Idempotency-Key` (up to 200 chars) for mutating operations (`/resolve`).
5. **Existing Codebase State:**
   - Backend test baseline: `backend/.venv/bin/pytest` currently executes 48 passing tests (`test_attachments.py`, `test_import_wizard.py`, `test_interaction_patch.py`, `test_reports_multiformat.py`, `test_working_slice.py`).
   - Specification verification checks: `docs/checks/verify_workflow.py`, `verify_reports.py`, `verify_plan.py` all exit with code 0 (`PASS`).
   - `backend/app/models.py`: Uses SQLAlchemy 2.0 mapped columns, `Base`, `new_id`, `utcnow`.
   - `backend/app/services.py`: Implements `begin_command` / `finish_command`, `scope_clause`, `allowed_owner`, `cas`.

---

## 2. Logic Chain

1. **Envelope Normalization:** External sources (Zion LMS, Laravel site) have disparate payloads. An adapter layer must normalize raw external data into `NormalizedEnvelope` (DTO v1.0) prior to inserting into `IntegrationInbox`.
2. **Database Dedup Guarantee:** Ingestion must be robust against duplicate webhook/polling calls. By placing a composite unique constraint `UniqueConstraint("source", "entity_type", "external_id", "source_revision", name="uq_integration_inbox_dedup")` in the database, replay attempts cannot corrupt state or create phantom records.
3. **Reconciliation Queue Separation:**
   - **Automated Path:** Educational metrics from LMS Zion can be ingested automatically because metrics are aggregate time-series associated with existing university and program codes.
   - **Manual / Supervised Path:** University applications from the Laravel website frequently contain unverified names or new universities not yet registered in CRM. To prevent data corruption, applications that cannot be matched deterministically must enter `IntegrationInbox` in `pending` status.
4. **Reconciliation Actions:**
   - When resolving an application, the supervisor chooses between:
     - `link_existing`: Links the application to an existing `Organization`, updates or creates `OrganizationContact`, and optionally creates a new `Interaction` with initial state `application_received`.
     - `create_new`: Creates a new `Organization`, new `OrganizationContact`, grants creator access, and optionally creates `Interaction`.
     - `reject`: Rejects the application with a documented audit reason.
   - This operation mutates core business records and must be protected by `Idempotency-Key` via `begin_command` / `finish_command`.
5. **RBAC & Security:**
   - Integration status, manual sync triggers, and reconciliation queues contain cross-organizational data. Exposing them to ordinary managers violates 152-FZ. Only users with role `supervisor` or `administrator` (or `admin`) are permitted to access `/api/v1/integrations/*`. A manager invoking these endpoints receives `403 FORBIDDEN`.
   - Metrics showcase (`GET /api/v1/integrations/metrics`) can be viewed by all authenticated users who have `reports.read`, but row-level scoping filters must ensure managers only see metrics for organizations within their permitted scope (`visible_organization_ids`).

---

## 3. Caveats

1. **Network Connectivity & Mock Stubs:** In the hackathon execution environment, live external endpoints for Zion LMS (`https://rtkb.zion-lms.ru/`) and the Laravel website are simulated via pluggable mock adapters (`MockLMSAdapter`, `MockWebsiteAdapter`). The adapter factory pattern (`get_adapter(source)`) ensures zero code changes are needed when live API credentials and endpoints are configured via environment variables.
2. **Program Matching for Applications:** Website applications may submit free-text program names (e.g. "DevOps и облачные технологии") or program codes (e.g. "program-devops"). The reconciliation logic should perform case-insensitive fallback matching against `Program.name` and `Program.id`.
3. **Manager Role Name Variations:** In the seed data and models, administrator is represented as `administrator` and supervisor as `supervisor`. Role checks must support `user.role in ("supervisor", "admin", "administrator")`.

---

## 4. Conclusion

The specification for the Resilient Integrations Contour is completely defined and directly actionable. The required components to implement are:
1. `backend/app/integrations/base.py`: DTO v1.0 `NormalizedEnvelope` and `BaseIntegrationAdapter`.
2. `backend/app/integrations/mock_lms.py`: `MockLMSAdapter` delivering realistic Zion LMS educational metrics fixtures.
3. `backend/app/integrations/mock_website.py`: `MockWebsiteAdapter` delivering Laravel website partnership applications (both existing and new universities).
4. `backend/app/integrations/factory.py`: Config-driven adapter factory (`get_adapter`).
5. `backend/app/models.py`: Added models `IntegrationInbox` (with dedup unique constraint) and `LearningMetric`.
6. `backend/app/integrations/service.py`: `sync_source`, `reconcile_application` (with CAS/Idempotency), and `get_learning_metrics_summary`.
7. `backend/app/main.py`: REST endpoints `/api/v1/integrations/status`, `/api/v1/integrations/sync/{source}`, `/api/v1/integrations/inbox`, `/api/v1/integrations/inbox/{id}/resolve`, `/api/v1/integrations/metrics`.
8. `frontend/src/views/IntegrationsView.tsx` & `frontend/src/App.tsx`: Gen2 Light Theme UI for status, inbox, modal resolution, and demand metrics.
9. `backend/tests/test_integrations.py`: Comprehensive test suite verifying all 12 QA scenarios.

---

## 5. Verification Method

To verify the implementation once built:
1. **Run Backend Test Suite:**
   ```bash
   backend/.venv/bin/pytest -v backend/tests/test_integrations.py
   backend/.venv/bin/pytest -v
   ```
   *Expected:* All existing 48 tests + new integration tests PASS (total > 55 tests, 100% OK).
2. **Run Planning Consistency Checks:**
   ```bash
   python3 docs/checks/verify_workflow.py
   python3 docs/checks/verify_reports.py
   python3 docs/checks/verify_plan.py
   ```
   *Expected:* All 3 checks exit with code 0 (`PASS`).
3. **Verify Zero New Dependencies:**
   Inspect `backend/requirements.txt` and `frontend/package.json` to verify no new dependencies were added.
4. **Inspect OpenAPI / Swagger UI:**
   Launch API and verify `/api/v1/integrations/*` routes appear in `/openapi.json` with documented request/response schemas.

---

# Detailed Specification & Fixtures

## A. DTO v1.0 Normalized Envelope Specification

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

@dataclass(frozen=True)
class NormalizedEnvelope:
    schema_version: str = "1.0"
    source: Literal["lms", "website"] = "lms"
    entity_type: Literal["learning_metric", "application"] = "learning_metric"
    external_id: str = ""
    source_revision: str = "1"
    operation: Literal["upsert", "delete"] = "upsert"
    effective_at: str = ""   # ISO-8601 UTC
    received_at: str = ""    # ISO-8601 UTC (populated upon arrival)
    payload: dict[str, Any] = field(default_factory=dict)
```

### JSON Representation Examples:

#### 1. LMS Learning Metric:
```json
{
  "schema_version": "1.0",
  "source": "lms",
  "entity_type": "learning_metric",
  "external_id": "zion-metric-org1-devops-cohorts",
  "source_revision": "1",
  "operation": "upsert",
  "effective_at": "2026-09-18T00:00:00Z",
  "received_at": "2026-09-20T00:50:00Z",
  "payload": {
    "organization_external_id": "org-1",
    "program_external_id": "program-devops",
    "metric_code": "active_cohorts",
    "value": 2.0,
    "unit": "cohort",
    "as_of": "2026-09-18T00:00:00Z",
    "definition_version": "proposal-1"
  }
}
```

#### 2. Website Application (Unknown University):
```json
{
  "schema_version": "1.0",
  "source": "website",
  "entity_type": "application",
  "external_id": "web-app-2026-089",
  "source_revision": "1",
  "operation": "upsert",
  "effective_at": "2026-09-19T14:20:00Z",
  "received_at": "2026-09-20T00:50:00Z",
  "payload": {
    "organization_name": "Казанский национальный исследовательский технический университет им. А.Н. Туполева",
    "organization_external_id": null,
    "representative_name": "Иванов Иван Иванович",
    "representative_position": "Заведующий кафедрой автоматизированных систем",
    "representative_email": "ivanov@kai.ru",
    "representative_phone": "+7 (843) 231-01-01",
    "program_name": "DevOps и облачные технологии",
    "program_id": "program-devops",
    "comments": "Просим рассмотреть возможность подключения нашего университета к проекту «ИТ Школа Ростелекома» в осеннем семестре 2026 года."
  }
}
```

---

## B. Database Models Specification

### 1. `IntegrationInbox`
- **Table:** `integration_inbox`
- **Columns:**
  - `id`: `String(64)`, Primary Key, default `new_id`
  - `source`: `String(32)`, index=True (`"lms"` | `"website"`)
  - `entity_type`: `String(64)`, index=True (`"learning_metric"` | `"application"`)
  - `external_id`: `String(128)`, index=True
  - `source_revision`: `String(64)`
  - `payload`: `JSON`
  - `status`: `String(32)`, default `"pending"`, index=True (`"pending"`, `"processed"`, `"quarantined"`, `"rejected"`)
  - `error_message`: `Text`, nullable=True
  - `matched_organization_id`: `ForeignKey("organizations.id")`, nullable=True, index=True
  - `matched_interaction_id`: `ForeignKey("interactions.id")`, nullable=True, index=True
  - `received_at`: `DateTime(timezone=True)`, default `utcnow`, index=True
  - `processed_at`: `DateTime(timezone=True)`, nullable=True
- **Table Constraints:**
  - `UniqueConstraint("source", "entity_type", "external_id", "source_revision", name="uq_integration_inbox_dedup")`

### 2. `LearningMetric`
- **Table:** `learning_metrics`
- **Columns:**
  - `id`: `String(64)`, Primary Key, default `new_id`
  - `organization_id`: `ForeignKey("organizations.id")`, index=True
  - `program_id`: `ForeignKey("programs.id")`, index=True
  - `metric_code`: `String(64)`, index=True (`"active_cohorts"`, `"students_enrolled"`, `"students_completed"`, `"attendance_rate"`)
  - `value`: `Float`
  - `unit`: `String(32)` (`"cohort"`, `"student"`, `"percent"`)
  - `as_of`: `DateTime(timezone=True)`, index=True
  - `source`: `String(32)`, default `"lms"`
  - `external_id`: `String(128)`, index=True
  - `created_at`: `DateTime(timezone=True)`, default `utcnow`
- **Indexes:**
  - `Index("ix_learning_metric_lookup", "organization_id", "program_id", "metric_code")`

---

## C. Mock Adapters & Fixture Catalog

### 1. `MockLMSAdapter` (Zion LMS Mock)
- **Source identifier:** `"lms"`
- **Endpoint:** `https://rtkb.zion-lms.ru/`
- **Fixtures:**
  1. `org-1` (МТУ) × `program-devops`:
     - `active_cohorts`: 2 (unit: "cohort")
     - `students_enrolled`: 45 (unit: "student")
     - `students_completed`: 38 (unit: "student")
     - `attendance_rate`: 91.5 (unit: "percent")
  2. `org-2` (Северный университет) × `program-qa`:
     - `active_cohorts`: 1 (unit: "cohort")
     - `students_enrolled`: 30 (unit: "student")
     - `students_completed`: 26 (unit: "student")
     - `attendance_rate`: 88.0 (unit: "percent")
  3. `org-3` (Поволжский государственный университет телекоммуникаций и информатики) × `program-devops`:
     - `active_cohorts`: 3 (unit: "cohort")
     - `students_enrolled`: 60 (unit: "student")
     - `students_completed`: 51 (unit: "student")
     - `attendance_rate`: 93.2 (unit: "percent")

### 2. `MockWebsiteAdapter` (Laravel Portal Mock)
- **Source identifier:** `"website"`
- **Endpoint:** `https://school.rt.ru/api/v1/applications`
- **Fixtures:**
  1. `web-app-001` (Known Organization match):
     - `organization_name`: "Московский технический университет"
     - `representative_name`: "Ковалев Андрей Сергеевич"
     - `representative_position`: "Декан факультета ИТ"
     - `representative_email`: "kovalev@mtu-edu.ru"
     - `representative_phone`: "+7 (495) 777-01-23"
     - `program_name`: "DevOps и облачные технологии"
     - `program_id`: "program-devops"
     - `comments`: "Заявка на расширение квоты для второго потока студентов."
     - *Behavior:* Deterministic match with `org-1` found. Matched organization set, status `pending` ready for supervisor approval.
  2. `web-app-002` (Unknown Organization):
     - `organization_name`: "Казанский национальный исследовательский технический университет"
     - `representative_name`: "Иванов Иван Иванович"
     - `representative_position`: "Заведующий кафедрой"
     - `representative_email`: "ivanov@kai.ru"
     - `representative_phone`: "+7 (843) 231-01-01"
     - `program_name`: "DevOps и облачные технологии"
     - `program_id`: "program-devops"
     - `comments`: "Просим рассмотреть возможность заключения партнерского договора."
     - *Behavior:* No match in `organizations`. Enters `pending` with `matched_organization_id=None`. Requires supervisor to resolve via `create_new` or `link_existing`.
  3. `web-app-003` (Ambiguous / Variant Name):
     - `organization_name`: "Северный университет"
     - `representative_name`: "Смирнова Ольга Павловна"
     - `representative_position`: "Специалист УМО"
     - `representative_email`: "smirnova@north-uni.ru"
     - `representative_phone`: "+7 (8182) 20-30-40"
     - `program_name`: "Инженерия качества ПО"
     - `program_id`: "program-qa"
     - `comments`: "Вопрос по согласованию учебных планов."
     - *Behavior:* Partial fuzzy match to `org-2` ("Северный университет прикладных наук"). Presented to supervisor as suggested match.

---

## D. REST API Endpoints Specification

| Method | Path | Auth / Role | Description | Error Codes |
|---|---|---|---|---|
| `GET` | `/api/v1/integrations/status` | supervisor, administrator | Returns health status, sync counters, and active mode of all adapters | `401 UNAUTHENTICATED`, `403 FORBIDDEN` (manager) |
| `POST` | `/api/v1/integrations/sync/{source}` | supervisor, administrator | Triggers manual synchronization of source (`"lms"` or `"website"`) | `401 UNAUTHENTICATED`, `403 FORBIDDEN`, `422 VALIDATION_ERROR` (bad source) |
| `GET` | `/api/v1/integrations/inbox` | supervisor, administrator | Paginated list of reconciliation items with filters (`source`, `status`) | `401 UNAUTHENTICATED`, `403 FORBIDDEN` |
| `POST` | `/api/v1/integrations/inbox/{id}/resolve` | supervisor, administrator | Resolves a pending application (`link_existing`, `create_new`, `reject`), with `Idempotency-Key` | `401 UNAUTHENTICATED`, `403 FORBIDDEN`, `404 NOT_FOUND`, `409 IDEMPOTENCY_CONFLICT`, `422 VALIDATION_ERROR` |
| `GET` | `/api/v1/integrations/metrics` | authenticated (`reports.read`) | Demand metrics showcase aggregated by program and university, respecting scope | `401 UNAUTHENTICATED`, `403 FORBIDDEN` |

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Envelope DTO | DTO v1.0 Normalization | Standardized ingestion envelope schema across all external sources | JSON envelope with `schema_version`, `source`, `entity_type`, `external_id`, `source_revision`, `operation`, `effective_at`, `payload` | Instantiated `NormalizedEnvelope` dataclass/model | `422 VALIDATION_ERROR` if required envelope fields missing or schema_version != "1.0" | Spec §7.2, lines 230-254 |
| 2 | Ingestion & Storage | `IntegrationInbox` Journal | Storing incoming raw envelopes before business mutations | Source envelope data | Persisted `IntegrationInbox` row with status `pending` or `processed` | Handled via DB rollback; unhandled DB errors return 500 without leaking stack traces | Spec §7.2, lines 258-262; ORIGINAL_REQUEST R1 |
| 3 | Deduplication | Composite Dedup Key | Strict database-level idempotency on `(source, entity_type, external_id, source_revision)` | Ingestion batch containing repeated envelopes | Skips duplicate without secondary side effects; increment `skipped_duplicates` counter | Identical key with differing payload raises `409 IDEMPOTENCY_CONFLICT` or marks record `quarantined` | Spec §7.2, lines 256-258; AC19 |
| 4 | Metrics Model | `LearningMetric` Persistence | Storing structured educational demand metrics from LMS | Validated learning metric payload (`organization_id`, `program_id`, `metric_code`, `value`, `unit`, `as_of`) | Persisted `LearningMetric` row | `422 VALIDATION_ERROR` if metric code or units are invalid | Dev Plan B29; Spec §7.2 |
| 5 | Mock LMS Adapter | `MockLMSAdapter` | Contract emulator for Zion LMS (`rtkb.zion-lms.ru`) with cohorts and student numbers | Optional `since: datetime` filter | List of normalized envelopes with metric codes `active_cohorts`, `students_enrolled`, `students_completed`, `attendance_rate` | Returns empty list or graceful degradation on simulated error | Dev Plan B27; ORIGINAL_REQUEST R2 |
| 6 | Mock Website Adapter | `MockWebsiteAdapter` | Contract emulator for Laravel website partner applications | Optional `since: datetime` filter | List of normalized envelopes with `entity_type="application"` | Returns empty list on simulated error | Dev Plan B28; ORIGINAL_REQUEST R2 |
| 7 | Adapter Factory | Configurable Adapter Factory | Pluggable switching between mock and live adapters via config | Source string (`"lms"`, `"website"`) | Instance implementing `BaseIntegrationAdapter` | `422 VALIDATION_ERROR` on unknown source identifier | Dev Plan B26; ORIGINAL_REQUEST R2 |
| 8 | Reconciliation | `link_existing` Resolution | Links application to an existing university in CRM and optionally provisions an interaction | `inbox_id`, `action="link_existing"`, `organization_id`, `create_interaction`, `owner_id`, `Idempotency-Key` | Updated `IntegrationInbox` (status=`processed`), linked `Interaction` | `404 NOT_FOUND` if org doesn't exist; `403 FORBIDDEN` if owner outside scope | Dev Plan B26; Spec §7.2; ORIGINAL_REQUEST R3 |
| 9 | Reconciliation | `create_new` Resolution | Creates new university, contact, creator access, and optional interaction | `inbox_id`, `action="create_new"`, `organization_name`, `create_interaction`, `owner_id`, `Idempotency-Key` | New `Organization`, new `OrganizationContact`, updated `IntegrationInbox`, new `Interaction` | `422 VALIDATION_ERROR` if organization name blank | Dev Plan B26; Spec §7.2; ORIGINAL_REQUEST R3 |
| 10 | Reconciliation | `reject` Resolution | Rejects application and stores operator reason | `inbox_id`, `action="reject"`, `reason`, `Idempotency-Key` | Updated `IntegrationInbox` (status=`rejected`, error_message=`reason`) | `422 VALIDATION_ERROR` if already processed | Dev Plan B26; Spec §7.2; ORIGINAL_REQUEST R3 |
| 11 | REST API | Adapter Status Gateway | Real-time status, health check, and sync counters of external adapters | `GET /api/v1/integrations/status` | JSON with list of adapters, modes, latencies, last sync timestamps, counters | `403 FORBIDDEN` for managers | Dev Plan B26; ORIGINAL_REQUEST R4 |
| 12 | REST API | Manual Sync Trigger | On-demand trigger to poll an external adapter | `POST /api/v1/integrations/sync/{source}` | Ingestion summary (`total`, `processed`, `pending`, `skipped_duplicates`, `errors`) | `403 FORBIDDEN` for managers; `422` for unknown source | Dev Plan B26; ORIGINAL_REQUEST R4 |
| 13 | REST API | Reconciliation Inbox Queue | List and filter pending/processed/rejected incoming applications | `GET /api/v1/integrations/inbox?source=...&status=...&page=...` | Paginated JSON with inbox items | `403 FORBIDDEN` for managers | Dev Plan B26; ORIGINAL_REQUEST R4 |
| 14 | REST API | Demand Metrics Showcase | Aggregated learning metrics by program, direction, and university | `GET /api/v1/integrations/metrics?organization_id=...&program_id=...` | Summary totals and breakdown by program and university | `403 FORBIDDEN` if user lacks `reports.read`; scoped to visible orgs | Dev Plan B29; ORIGINAL_REQUEST R4 |
| 15 | Security & RBAC | 152-FZ Isolation for Integrations | Enforcing supervisor/admin-only access to global integration controls | User session via JWT / demo identity | Allowed or rejected | Manager calling integration controls receives `403 FORBIDDEN` | AGENTS.md §3; AC12, AC18 |
| 16 | Idempotency | CAS & Key Protection on Resolve | Prevent race conditions during concurrent resolutions | `Idempotency-Key` header (<= 200 chars) | Same response returned without duplicate entity creation | `409 IDEMPOTENCY_CONFLICT` on concurrent attempt or changed body | AGENTS.md §2.2; AC19 |
| 17 | UI / UX | Integrations Management View | Dedicated view in Rostelecom Gen2 Light Theme with tabs, modals, and charts | Navigation to `/integrations` | Responsive SPA view with status cards, inbox table, resolution modal, and charts | Displays error alert on failure without clearing user input | ORIGINAL_REQUEST R5; ADR 001 |

---

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Envelope Normalization | Missing required field `schema_version` or unsupported version `"2.0"` | Rejected with `APIError("VALIDATION_ERROR", "Неподдерживаемая версия схемы конверта: ожидается 1.0", 422)`. |
| 2 | Deduplication | Same envelope delivered twice in identical payload | Second delivery detects existing record in `IntegrationInbox` matching `(source, entity_type, external_id, source_revision)`; skips insert without error; increments `skipped_duplicates`. |
| 3 | Deduplication | Same dedup key delivered with conflicting payload content | Ingestion flags conflict; marks inbox status as `"quarantined"` with `error_message="Конфликт содержимого для существующего ключа доставки"`. |
| 4 | Metric Ingestion | Metric references unknown `organization_external_id` (e.g. `"org-unknown-99"`) | Inbox record created with `status="pending"`, `error_message="Организация с внешним идентификатором org-unknown-99 не найдена"`. No phantom row created in `LearningMetric`. |
| 5 | Website Application | University name matches existing university exactly (e.g. `"Московский технический университет"`) | Inbox record created with `matched_organization_id="org-1"`, status `"pending"`. Modal pre-selects `org-1` for operator convenience. |
| 6 | Website Application | University name is entirely new / unknown (e.g. `"Казанский национальный исследовательский технический университет"`) | Inbox record created with `matched_organization_id=None`, status `"pending"`. Modal displays option to create new organization. |
| 7 | Application Resolution | Operator attempts to resolve an application that is already in `status="processed"` or `"rejected"` | Returns `APIError("VALIDATION_ERROR", "Заявка уже обработана или отклонена.", 422)`. |
| 8 | Application Resolution | Missing `Idempotency-Key` header | Returns `APIError("VALIDATION_ERROR", "Нужен непустой заголовок Idempotency-Key (до 200 символов).", 422)`. |
| 9 | Application Resolution | Replay with same `Idempotency-Key` and identical body | Returns previously saved resolution response immediately from `CommandResult` cache without re-creating interactions or contacts. |
| 10 | Application Resolution | Replay with same `Idempotency-Key` and modified payload | Returns `APIError("IDEMPOTENCY_CONFLICT", "Этот ключ уже использован с другим содержимым.", 409)`. |
| 11 | RBAC Isolation | Manager (`manager-a` or `manager-b`) calls `POST /api/v1/integrations/sync/lms` | Returns `APIError("FORBIDDEN", "Недостаточно прав для управления интеграциями.", 403)`. |
| 12 | RBAC Isolation | Manager calls `POST /api/v1/integrations/inbox/{id}/resolve` | Returns `APIError("FORBIDDEN", "Недостаточно прав для управления интеграциями.", 403)`. |
| 13 | Metrics Query | Manager calls `GET /api/v1/integrations/metrics` | Returns metrics ONLY for universities where manager has `scope_clause` or `OrganizationAccess` permissions. Disallowed organizations are excluded from aggregation. |
| 14 | Adapter Sync | Simulated external service outage (HTTP 503 or network failure) | Adapter marks health as `"degraded"` or `"unavailable"`; sync returns diagnostic error summary without crashing FastAPI worker or corrupting existing transactions. |
| 15 | Idempotency Key Length | `Idempotency-Key` longer than 200 characters | Returns `APIError("VALIDATION_ERROR", "Нужен непустой заголовок Idempotency-Key (до 200 символов).", 422)`. |
