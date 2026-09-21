# DISPATCH: Milestone 2 — Sync & Reconciliation Engine Engineer

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Context & Inputs
- Authoritative Request: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md` (Section `## 2026-09-19T21:49:49Z`)
- Project Scope & Architecture: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md`
- Milestone 1 Handoff: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_1/handoff.md`
- Backend Explorer Blueprint: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_3_1/handoff.md`
- Code Rules: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md` (Ponytail Ladder: stdlib-first, 0 new dependencies in requirements.txt)

## Identity
- Role: Sync & Reconciliation Engine Engineer
- Working Directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_2`
- Parent Orchestrator: orchestrator_3

## Exclusive File Write Ownership
You have exclusive write ownership over:
- `backend/app/integrations/service.py`
- `backend/app/services.py` (adding `integrations.manage` permission to `permissions()`)
- `backend/app/main.py` (adding REST endpoints under `/api/v1/integrations/`)

DO NOT modify files outside your ownership scope.

## Deliverables & Tasks
1. **`backend/app/services.py`**:
   - In `permissions(user)`: add `"integrations.manage"` to `supervisor` and `administrator` sets.
   - Line managers (`manager`) must NOT have `"integrations.manage"`.

2. **`backend/app/integrations/service.py`**:
   Implement:
   - `get_integrations_status(db: Session, user: User, config: Settings) -> dict[str, Any]`:
     - Checks `require_permission(user, "integrations.manage")`.
     - Queries `factory.get_adapter()` for `"lms"` and `"website"`.
     - Calls `health_check()` on each.
     - Aggregates metrics from `IntegrationInbox` (total, pending, processed, quarantined, rejected) and `LearningMetric`.
     - Returns dictionary with `adapters`, `total_inbox`, `total_pending`, `total_processed`, `total_metrics`, `last_synced_at`.
   - `sync_source(db: Session, user: User, source: str, config: Settings) -> dict[str, Any]`:
     - Checks `require_permission(user, "integrations.manage")`.
     - Resolves adapter via `factory.get_adapter(source, config)`.
     - Calls `adapter.fetch_updates()`.
     - Ingests envelopes into `IntegrationInbox`:
       - Checks for duplicate by `(source, entity_type, external_id, source_revision)`.
       - If already exists, skip to preserve idempotency and prevent duplicate key violations.
       - Inserts new `IntegrationInbox` record.
       - If `entity_type == "learning_metric"`:
         - Looks up `Organization` and `Program`.
         - If found, upserts `LearningMetric` by `(source, external_id)` with `as_of`, `value`, `unit`, etc.
         - Sets `inbox_item.status = "processed"`, `processed_at = utcnow()`.
       - If `entity_type == "application"`:
         - Checks for partial/exact match on `Organization.name`. If found, sets `matched_organization_id = org.id`.
         - Keeps `status = "pending"` for operator reconciliation.
     - Commits changes to DB.
     - Returns `{"source": source, "received_count": ..., "processed_count": ..., "pending_count": ..., "message": "..."}`.
   - `reconcile_application(db: Session, user: User, inbox_id: str, action: str, params: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]`:
     - Checks `require_permission(user, "integrations.manage")`.
     - Fetches `IntegrationInbox` item by `inbox_id`. Ensures it exists, is `"application"`, and is in `"pending"` status.
     - Supports actions:
       - `"link_existing"`: Links to existing `Organization`. Optionally creates `OrganizationContact` and `Interaction` (validating `allowed_owner`). Sets `status = "processed"`.
       - `"create_new"`: Creates new `Organization` + `OrganizationAccess` for creator + `OrganizationContact`. Optionally creates `Interaction` with validated owner. Sets `status = "processed"`.
       - `"reject"`: Sets `status = "rejected"`, `error_message = params.get("reason", "Rejected by operator")`.
     - Records `processed_at = utcnow()`.
     - Commits changes.
     - Returns resolved record details.
   - `get_learning_metrics_summary(db: Session, user: User, organization_id: str | None = None, program_id: str | None = None) -> dict[str, Any]`:
     - Checks `require_permission(user, "reports.read")`.
     - Filters by `organization_id` and `program_id` if provided.
     - Scopes by user permissions (if manager, only allowed organizations).
     - Returns summary: `total_cohorts`, `total_enrolled`, `total_completed`, `avg_attendance_rate`, and breakdown lists by program and organization.

3. **`backend/app/main.py`**:
   Mount the 5 endpoints under prefix `/api/v1/integrations`:
   - `GET /api/v1/integrations/status`
   - `POST /api/v1/integrations/sync/{source}` (optional or supported `Idempotency-Key`)
   - `GET /api/v1/integrations/inbox` (supports query params `source`, `status`, `page`, `page_size`)
   - `POST /api/v1/integrations/inbox/{id}/resolve` (requires header `Idempotency-Key`, wraps with `begin_command` / `finish_command`)
   - `GET /api/v1/integrations/metrics` (query params `organization_id`, `program_id`)
   - Ensure manager role gets `403 Forbidden` (`APIError("FORBIDDEN", ...)`) on integration management endpoints.

4. **Verification**:
   - Run backend tests: `backend/.venv/bin/pytest backend/tests/` -> all 48 tests pass.
   - Test new endpoints via Python or in-memory FastAPI TestClient to ensure:
     - `GET /api/v1/integrations/status` returns 200 for supervisor, 403 for manager.
     - `POST /api/v1/integrations/sync/lms` ingests metrics and deduplicates.
     - `POST /api/v1/integrations/sync/website` creates pending applications in inbox.
     - `POST /api/v1/integrations/inbox/{id}/resolve` successfully executes `link_existing`, `create_new`, and `reject`.
   - Run `python3 docs/checks/verify_workflow.py`, `verify_reports.py`, `verify_plan.py` -> all PASS.
   - Write full handoff report to `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_2/handoff.md`.
   - Send completion message to orchestrator_3 via `send_message`.

## 2026-09-20T00:59:49Z
You are the Sync & Reconciliation Engine Engineer for the Resilient Integrations Contour (Milestone 2).
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_2.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_2/DISPATCH.md, /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md, and /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md.
Follow AGENTS.md (Ponytail Ladder: stdlib-first, 0 new dependencies in requirements.txt).
Implement backend/app/integrations/service.py, update permissions in backend/app/services.py, and mount REST API endpoints under /api/v1/integrations/ in backend/app/main.py.
Run the backend test suite (backend/.venv/bin/pytest backend/tests/) to verify 0 regressions across all 48 tests.
Write your complete handoff report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_2/handoff.md.
When finished, send a message to orchestrator_3 via send_message.
