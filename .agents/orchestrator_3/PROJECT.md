# Project: Resilient Integrations Contour (B26–B29)
# Scope: Full Milestone 3 Integration Architecture

## Architecture
- **Adapter Layer (`backend/app/integrations/`)**:
  - Normalized Envelope DTO v1.0 (`NormalizedEnvelope`) adhering to TZ §7.2.
  - `BaseIntegrationAdapter` abstract interface: `fetch_updates(since)`, `health_check()`.
  - `MockLMSAdapter`: emulates Zion LMS (`https://rtkb.zion-lms.ru/`), generating educational metrics for universities and programs.
  - `MockWebsiteAdapter`: emulates Laravel portal, generating partnership applications.
  - `factory.py`: `get_adapter(source)` with configuration-driven mode switching (`mock` / `live`).
- **Data & Reconciliation Layer**:
  - `IntegrationInbox`: staging queue for external packets with composite unique constraint `(source, entity_type, external_id, source_revision)` enforcing strict deduplication.
  - `LearningMetric`: storage for aggregated educational metrics (active cohorts, students enrolled, students completed, attendance rate).
  - `service.py`: `sync_source()` for ingest & auto-processing, `reconcile_application()` with CAS/Idempotency-Key for operator resolutions (`link_existing`, `create_new`, `reject`), and `get_learning_metrics_summary()`.
- **API & Security Layer (`backend/app/main.py`)**:
  - Endpoints under `/api/v1/integrations/` (`status`, `sync/{source}`, `inbox`, `inbox/{id}/resolve`, `metrics`).
  - RBAC: `integrations.manage` granted strictly to `supervisor` and `administrator`. Line managers receive `403 Forbidden` preserving 152-ФЗ scope isolation.
  - Mutating operations (`resolve`, `sync`) protected by `Idempotency-Key`.
- **User Interface Layer (`frontend/src/`)**:
  - `IntegrationsView.tsx`: Adapter status cards, Reconciliation inbox table with status tabs, Resolution modal, Demand metrics dashboard.
  - `App.tsx`: Role-filtered «Интеграции» tab for supervisor/administrator, friendly 403 panel.
  - Rostelecom Gen2 Light Theme tokens (`#7700FF`, `#FF4F12`, `#F4F5F8`, `#101828`).

## Feature Inventory
| # | Feature | Description | Milestone | Source | Status |
|---|---|---|---|---|---|
| F01 | DTO v1.0 Envelope | Normalized dataclass with schema_version 1.0, operation, timestamps, payload per TZ 7.2 | M1 | Survey | VERIFIED |
| F02 | BaseIntegrationAdapter | Abstract adapter base class with fetch_updates and health_check | M1 | Survey | VERIFIED |
| F03 | MockLMSAdapter | Pluggable mock for Zion LMS educational metrics fixtures (org-1, org-2, org-3) | M1 | Survey | VERIFIED |
| F04 | MockWebsiteAdapter | Pluggable mock for Laravel website applications with known and unknown orgs | M1 | Survey | VERIFIED |
| F05 | Adapter Factory | Config-driven get_adapter(source) supporting mock and live modes | M1 | Survey | VERIFIED |
| F06 | IntegrationInbox Model | SQLAlchemy model with composite unique constraint (source, entity_type, external_id, source_revision) | M1 | Survey | VERIFIED |
| F07 | LearningMetric Model | SQLAlchemy model for educational metrics with index on (organization_id, program_id, metric_code) | M1 | Survey | VERIFIED |
| F08 | Config Mode Toggles | Settings in config.py for LMS_INTEGRATION_MODE and WEBSITE_INTEGRATION_MODE | M1 | Survey | VERIFIED |
| F09 | Ingestion & Sync Engine | sync_source() in service.py ingesting envelopes into inbox and auto-processing metrics | M2 | Survey | VERIFIED |
| F10 | Deduplication Logic | Database unique constraint + graceful duplicate skip on repeat ingestion | M2 | Survey | VERIFIED |
| F11 | Reconciliation Engine | reconcile_application() handling link_existing, create_new, and reject with Idempotency-Key | M2 | Survey | VERIFIED |
| F12 | Metrics Aggregation | get_learning_metrics_summary() aggregating demand metrics by org and program | M2 | Survey | VERIFIED |
| F13 | RBAC Permissions | Grant integrations.manage to supervisor and administrator; enforce 403 for manager | M2 | Survey | VERIFIED |
| F14 | Integration REST Endpoints | 5 endpoints in main.py: /status, /sync/{source}, /inbox, /inbox/{id}/resolve, /metrics | M2 | Survey | VERIFIED |
| F15 | Frontend Types & API | DTO interfaces in types.ts, typed methods with Idempotency-Key in api.ts | M3 | Survey | VERIFIED |
| F16 | IntegrationsView Screen | Status cards, Reconciliation table, Resolution modal, and Metrics showcase | M3 | Survey | VERIFIED |
| F17 | Navigation Integration | Role-filtered tab in App.tsx with 403 fallback for line managers | M3 | Survey | VERIFIED |
| F18 | Automated Test Suite | test_integrations.py with >= 10 tests verifying all integration workflows (total tests > 55) | M3 | Survey | VERIFIED |
| F19 | Ponytail Compliance | Zero new dependencies in requirements.txt and package.json | M3 | Survey | VERIFIED |
| F20 | Verification Scripts | 100% pass on verify_workflow.py, verify_reports.py, verify_plan.py | M3 | Survey | VERIFIED |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | Backend Adapter & Schema Architect | Models (IntegrationInbox, LearningMetric), config settings, integrations package (base, mock_lms, mock_website, factory) | none | DONE |
| M2 | Sync & Reconciliation Engine Engineer | Service (sync_source, reconcile_application, get_metrics, get_status), RBAC permissions, REST API endpoints, Idempotency-Key | M1 | DONE |
| M3 | Frontend UI & QA Forensic Engineer | Types, API methods, IntegrationsView, App.tsx navigation, Gen2 CSS, test_integrations.py (>55 tests total PASS, verify_*.py PASS) | M2 | DONE |
| M4 | Verification & Audit Gate | Multi-agent Architecture Review, Adversarial Challenge, and Forensic Integrity Audit | M3 | DONE |

## Interface Contracts
### `BaseIntegrationAdapter`
- `fetch_updates(since: datetime | None = None) -> list[NormalizedEnvelope]`
- `health_check() -> dict[str, Any]`

### `NormalizedEnvelope` (DTO v1.0)
- `schema_version`: `"1.0"`
- `source`: `"lms"` | `"website"`
- `entity_type`: `"learning_metric"` | `"application"`
- `external_id`: `str`
- `source_revision`: `str`
- `operation`: `"upsert"`
- `effective_at`: `datetime`
- `received_at`: `datetime`
- `payload`: `dict[str, Any]`

### Integration Service Contracts
- `sync_source(db: Session, user: User, source: str) -> dict[str, Any]`
- `reconcile_application(db: Session, user: User, inbox_id: str, action: str, params: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]`
- `get_learning_metrics_summary(db: Session, user: User, organization_id: str | None = None, program_id: str | None = None) -> dict[str, Any]`
- `get_integrations_status(db: Session, user: User) -> dict[str, Any]`

### REST Endpoints
- `GET /api/v1/integrations/status` -> `200 OK`
- `POST /api/v1/integrations/sync/{source}` -> `200 OK` (requires `Idempotency-Key`)
- `GET /api/v1/integrations/inbox?source=...&status=...&page=...` -> `200 OK`
- `POST /api/v1/integrations/inbox/{id}/resolve` -> `200 OK` (requires `Idempotency-Key`)
- `GET /api/v1/integrations/metrics?organization_id=...&program_id=...` -> `200 OK`

## Code Layout
- `backend/app/models.py`: Added `IntegrationInbox` and `LearningMetric`
- `backend/app/config.py`: Added `lms_integration_mode`, `website_integration_mode`, URLs
- `backend/app/integrations/__init__.py`: Package init
- `backend/app/integrations/base.py`: DTO envelope & Base adapter
- `backend/app/integrations/mock_lms.py`: Mock LMS adapter
- `backend/app/integrations/mock_website.py`: Mock Website adapter
- `backend/app/integrations/factory.py`: Adapter factory
- `backend/app/integrations/service.py`: Sync, reconciliation, metrics service
- `backend/app/services.py`: RBAC `integrations.manage`
- `backend/app/main.py`: Integrations router endpoints
- `backend/tests/test_integrations.py`: Automated integration test suite
- `frontend/src/types.ts`: TypeScript interfaces
- `frontend/src/api.ts`: API client functions
- `frontend/src/views/IntegrationsView.tsx`: Integrations dashboard & resolution modal
- `frontend/src/App.tsx`: Navigation menu integration
- `frontend/src/styles.css`: Gen2 CSS styles
