# Project: Gate P / Gate O Readiness Sprint (Tasks B17, B31, B33, B34, B36)

## Architecture Overview
This sprint delivers the Gate P / Gate O readiness contour for `rost_crm`:
- **Workflow Migration Engine**: Versioning (v1 15 states, v2 extended transitions), dry-run preview, atomic transactional commit with CAS revision update, immutable `workflow_migrated` audit events, idempotency caching, and RBAC (`supervisor`, `administrator` only).
- **Load & Concurrency Benchmark**: Standalone `backend/benchmarks/benchmark_load.py` simulating 50 concurrent users (40 managers, 8 supervisors, 2 admins) and 10 simultaneous analytical reports with P95 <= 1.0s, generating `docs/benchmarks/load-test-report.md`.
- **Role-Based Interactive Knowledge Base**: Overhaul `frontend/src/views/ReferenceViews.tsx:HelpPage` with role tabs (Manager, Supervisor, Administrator), Gen2 light theme visual cards, and error code accordion.
- **Workflow Migrator UI**: 3-step modal wizard in the admin area supporting version selection, mapping matrix, dry-run preview with collision warnings, and SPA commit without page reload.
- **152-FZ Compliance Matrix**: `docs/security/152-fz-compliance-matrix.md` mapping 152-FZ, 149-FZ, and FSTEC Order #117 to concrete code mechanisms (HTTP 404 scoping, in-memory JWT, magic-bytes/file validation, immutable audit log, data depersonalization).
- **ArchiMate 3.1 & C4 Architecture Docs**: `docs/architecture/rost_crm_architecture.archimate` (valid XML exchange format) and `docs/architecture/c4-architecture.md` (Mermaid C4 L1, L2, L3).
- **Quality & Non-regression**: All existing 99 pytest tests pass, specification oracles pass, zero dependency growth.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| F01 | Workflow Versioning (v1 & v2) | V1 authoritative 15 states; V2 7 fast-track/rework transitions | M1 | B17 / R06 |
| F02 | Migration Preview Engine | `preview_workflow_migration`: validation, 422 on terminal->active, distributions, collisions | M1 | B17 / R06 / AC08 |
| F03 | Migration Commit Engine | `commit_workflow_migration`: atomic transactional commit, CAS revision increment, `workflow_migrated` audit event, data preservation | M1 | B17 / R06 / AC08 |
| F04 | Migration REST Endpoints | `POST /api/v1/workflow/migrate/preview` and `/commit`, RBAC supervisor/admin only | M1 | B17 / R06 |
| F05 | Idempotency Handling | Support for `Idempotency-Key` header with replay of cached responses | M1 | B17 / R06 |
| F06 | Automated Migration Tests | `backend/tests/test_workflow_migration.py` covering positive, negative, RBAC, CAS, data integrity | M1 | B17 / R07 |
| F07 | Standalone Load Benchmark Script | `backend/benchmarks/benchmark_load.py` using asyncio & httpx, supporting in-process and live HTTP | M1 | B31 / R18 / R19 / AC23 / AC24 |
| F08 | 50 Users + 10 Reports Workload | 40 managers, 8 supervisors, 2 admins + 10 heavy reports with AnyIO threadpool tuning | M1 | B31 / R19 |
| F09 | Benchmark Report Protocol | `docs/benchmarks/load-test-report.md` proving P95 <= 1.0s and 0% error rate | M1 | B31 / R18 / AC23 |
| F10 | HelpPage Role Tabs | Manager, Supervisor, Administrator tabs with dedicated workflows and invariants | M2 | B34 / R21 / AC21 |
| F11 | Gen2 Visual Scenario Cards | Visual cards with icons, Gen2 palette (#7700FF, #FF4F12, #F4F5F8), Important/Warning badges | M2 | B34 / R21 |
| F12 | Error Code Accordion | Interactive accordion for CAS 409, Mapping 422, File 413, Quarantine 422, Scope 404 | M2 | B34 / R21 / AC21 |
| F13 | Workflow Migrator Modal Wizard | 3-step wizard in admin area: Step 1 Mapping, Step 2 Preview, Step 3 Confirm/Commit (SPA) | M2 | B17 UI / R06 |
| F14 | Frontend API & Types Extension | Add `previewWorkflowMigration`, `commitWorkflowMigration` to `api.ts` and types to `types.ts` | M2 | B17 UI |
| F15 | 152-FZ Regulatory Compliance Matrix | `docs/security/152-fz-compliance-matrix.md` linking regulations to exact code lines | M3 | B33 / R27 / AC27 |
| F16 | Security Mechanisms Traceability | Trace 404 scoping, in-memory JWT, magic bytes/quarantine, immutable audit, depersonalization | M3 | B33 / R27 |
| F17 | ArchiMate 3.1 Model Exchange File | `docs/architecture/rost_crm_architecture.archimate` conforming to Open Group standard XML | M3 | B36 / R26 / AC26 |
| F18 | C4 Model Architecture Diagrams | `docs/architecture/c4-architecture.md` containing Mermaid diagrams for C4 L1, L2, L3 | M3 | B36 / R26 |
| F19 | Test Suite Non-Regression | Ensure all 99 existing tests pass + new migration tests pass (100% PASS) | M4 | DoD / R07 |
| F20 | Verification Oracles & Ponytail Guard | Verify `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` PASS; 0 new dependencies | M4 | DoD / AGENTS.md |

## Milestones
| # | Name | Scope | Specialist Role | Dependencies | Status |
|---|---|---|---|---|---|
| M1 | Process & Performance Architect | Tasks B17 backend, B31 benchmark, R7 tests (F01–F09) | `worker_backend_4_1` | None | PLANNED |
| M2 | UX & Knowledge Base Engineer | Tasks B34 HelpPage, B17 UI wizard (F10–F14) | `worker_frontend_4_1` | M1 contracts | PLANNED |
| M3 | Security & Architecture Specialist | Tasks B33 152-FZ matrix, B36 ArchiMate & C4 (F15–F18) | `worker_security_4_1` | None | PLANNED |
| M4 | Independent Verification & Audit Gate | Full test execution, adversarial stress, review, forensic audit (F19–F20) | Reviewers, Challengers, Auditor | M1, M2, M3 | PLANNED |

## Interface Contracts

### 1. Workflow Versioning & Migration API
- `POST /api/v1/workflow/migrate/preview`:
  - Request:
    ```json
    {
      "from_version": 1,
      "to_version": 2,
      "status_mapping": {
        "contact_search": "contact_search",
        "document_revision": "document_signing"
      }
    }
    ```
  - Response (200 OK):
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
  - Error (422 Unprocessable Entity):
    ```json
    {
      "error": {
        "code": "VALIDATION_ERROR",
        "message": "Недопустимо сопоставлять терминальный статус 'completed' в активный статус 'document_signing'."
      }
    }
    ```

- `POST /api/v1/workflow/migrate/commit`:
  - Header: `Idempotency-Key: <uuid>` (mandatory)
  - Request:
    ```json
    {
      "from_version": 1,
      "to_version": 2,
      "status_mapping": { ... }
    }
    ```
  - Response (200 OK):
    ```json
    {
      "status": "migrated",
      "from_version": 1,
      "to_version": 2,
      "migrated_count": 5,
      "status_distribution": {"contact_search": 2, "document_signing": 3},
      "details": [...]
    }
    ```

### 2. Frontend API Client (`frontend/src/api.ts`)
```typescript
previewWorkflowMigration: (token: string, body: {
  from_version: number;
  to_version: number;
  status_mapping: Record<string, string>;
}) => Promise<WorkflowMigrationPreview>;

commitWorkflowMigration: (token: string, body: {
  from_version: number;
  to_version: number;
  status_mapping: Record<string, string>;
}, idempotencyKey: string) => Promise<WorkflowMigrationResult>;
```

### 3. Load Benchmark CLI
```bash
python benchmarks/benchmark_load.py --duration 10 --output ../docs/benchmarks/load-test-report.md [--in-process | --url http://127.0.0.1:8000]
```

## Code Layout
- Backend Models & Workflow: `backend/app/models.py`, `backend/app/workflow.py`, `backend/app/services.py`, `backend/app/main.py`
- Backend Benchmark: `backend/benchmarks/benchmark_load.py`
- Backend Tests: `backend/tests/test_workflow_migration.py`
- Frontend Types & API: `frontend/src/types.ts`, `frontend/src/api.ts`
- Frontend Views: `frontend/src/views/ReferenceViews.tsx`, `frontend/src/views/WorkflowGraphView.tsx` or `frontend/src/views/CatalogPage.tsx`
- Security Docs: `docs/security/152-fz-compliance-matrix.md`
- Architecture Docs: `docs/architecture/rost_crm_architecture.archimate`, `docs/architecture/c4-architecture.md`
- Benchmark Report: `docs/benchmarks/load-test-report.md`
