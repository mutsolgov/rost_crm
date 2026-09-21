# DISPATCH: Milestone 3 — Frontend UI & QA Forensic Engineer

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Context & Inputs
- Authoritative Request: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md` (Section `## 2026-09-19T21:49:49Z`)
- Project Scope & Architecture: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md`
- Frontend Explorer Blueprint: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_3_1/handoff.md`
- Backend Explorer Blueprint: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_3_1/handoff.md`
- Milestone 1 Handoff: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_1/handoff.md`
- Milestone 2 Handoff: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_2/handoff.md`
- Code Rules: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md` (Ponytail Ladder: stdlib-first, 0 new dependencies in requirements.txt and package.json; Rostelecom Gen2 Light Theme).

## Identity
- Role: Frontend UI & QA Forensic Engineer
- Working Directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_qa_3`
- Parent Orchestrator: orchestrator_3

## Exclusive File Write Ownership
You have exclusive write ownership over:
- `frontend/src/types.ts`
- `frontend/src/api.ts`
- `frontend/src/views/IntegrationsView.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `backend/tests/test_integrations.py`

DO NOT modify files outside your ownership scope.

## Deliverables & Tasks

### Part 1: Frontend Implementation
1. **`frontend/src/types.ts`**:
   - Add typed interfaces for integrations: `IntegrationSource`, `IntegrationEntityType`, `InboxStatus`, `ReconciliationAction`, `IntegrationAdapterStatus`, `IntegrationsStatusResponse`, `IntegrationSyncResponse`, `ApplicationPayload`, `IntegrationInboxItem`, `IntegrationInboxResponse`, `ReconcileResolveParams`, `LearningMetricItem`, `LearningMetricsSummaryResponse`.

2. **`frontend/src/api.ts`**:
   - Add typed helper methods in `ApiClient`:
     - `getIntegrationsStatus(): Promise<IntegrationsStatusResponse>`
     - `syncIntegrationSource(source: string): Promise<IntegrationSyncResponse>`
     - `getIntegrationInbox(params?: { source?: string; status?: string; page?: number; page_size?: number }): Promise<IntegrationInboxResponse>`
     - `resolveInboxItem(id: string, body: { action: string; organization_id?: string; organization_name?: string; org_type?: string; contact_name?: string; email?: string; phone?: string; owner_id?: string; program_id?: string; product_id?: string; title?: string; reason?: string }): Promise<any>` (with `makeMutationKey()`)
     - `getIntegrationMetrics(params?: { organization_id?: string; program_id?: string }): Promise<LearningMetricsSummaryResponse>`

3. **`frontend/src/views/IntegrationsView.tsx`**:
   - Implement the complete «Шлюз интеграций и сверка» screen adhering to Rostelecom Gen2 Light Theme:
     - Section 1: External System Status Cards (Zion LMS & Laravel Website) with status indicator dot, badge «Эмуляция контракта», last sync timestamp, queue counters, and «Синхронизировать сейчас» action button with loading state.
     - Section 2: Learning Metrics Showcase with KPI summary cards (active cohorts, enrolled students, completed students, attendance rate) and breakdown bars by program and university in Gen2 palette (`#7700FF`, `#FF4F12`).
     - Section 3: Reconciliation Inbox Table with status filter tabs (Все, Требуют внимания / pending, Сопоставлено / processed, Отклонено / rejected), search input, and action button «Разрешить» for pending applications.
     - Section 4: Modal Resolution Dialog (`ResolveModal`):
       - Choice between:
         a) «Привязать к существующему вузу» (selection from catalogs.organizations).
         b) «Создать новую организацию и контакт» (inputs for org name, org type, contact name, email, phone).
         c) «Отклонить заявку» (input for rejection reason).
       - Optional interaction creation toggle with manager assignment dropdown (`catalogs.owners`).
       - Submit with `Idempotency-Key` and error handling without page reload (SPA invariant).

4. **`frontend/src/App.tsx`**:
   - Wire «Интеграции» into navigation array: only visible when `isPrivileged = me.role === 'supervisor' || me.role === 'administrator' || me.role === 'admin'`.
   - Render `IntegrationsView` when `activeNav === 'integrations'`.
   - Render 403 fallback panel if unauthorized user visits `#/integrations`.

5. **`frontend/src/styles.css`**:
   - Add necessary styles using Gen2 CSS tokens (`--rtk-color-primary`, `--rtk-color-accent`, etc.).

6. **Frontend Verification**:
   - Verify TypeScript syntax with `node --experimental-strip-types --check frontend/src/api.ts` and `frontend/src/types.ts`.
   - Confirm 0 new dependencies in `frontend/package.json`.

---

### Part 2: QA & Automated Integration Test Suite
1. **`backend/tests/test_integrations.py`**:
   Create comprehensive automated tests covering:
   - `test_integrations_status_rbac`: Supervisor and Admin get 200 OK; Manager gets 403 Forbidden.
   - `test_lms_sync_and_learning_metrics`: Triggering `/sync/lms` ingests envelopes and populates `LearningMetric`.
   - `test_sync_deduplication_and_idempotency`: Triggering repeat `/sync/lms` skips duplicates cleanly (0 duplicates created in DB).
   - `test_website_sync_creates_pending_inbox_items`: Syncing website creates applications in `IntegrationInbox` in `pending` status.
   - `test_inbox_pagination_and_filtering`: Querying `/inbox` with status and source filters.
   - `test_reconcile_link_existing_with_interaction`: Resolving an application with `link_existing` links org, creates contact, creates interaction in `contact_search`.
   - `test_reconcile_create_new_organization`: Resolving with `create_new` creates organization, contact, and interaction.
   - `test_reconcile_reject`: Resolving with `reject` transitions status to `rejected` with error message.
   - `test_reconcile_conflict_already_processed`: Attempting to resolve an already-resolved item returns 409 Conflict.
   - `test_reconcile_idempotency_key_replay`: Re-sending resolution with same `Idempotency-Key` returns cached result without creating duplicate interactions.
   - `test_learning_metrics_summary_aggregation`: Calling `/metrics` returns valid totals and program breakdowns.
   - `test_scope_isolation_152_fz_on_created_interaction`: Verifying manager isolation on interactions created via integration (manager outside team receives 404).

2. **Full Regression Execution**:
   - Run `backend/.venv/bin/pytest backend/tests/` to verify:
     - All 48 existing tests PASS.
     - All new tests in `test_integrations.py` PASS.
     - Total passed tests > 55 (target >= 58).
     - 0 failures, 0 errors.

3. **Specification Verification**:
   - Run `python3 docs/checks/verify_workflow.py` -> PASS
   - Run `python3 docs/checks/verify_reports.py` -> PASS
   - Run `python3 docs/checks/verify_plan.py` -> PASS

4. **Ponytail Check**:
   - `git diff backend/requirements.txt` -> empty.
   - `git diff frontend/package.json` -> empty.

Write complete handoff report to `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_qa_3/handoff.md`.
Send completion message to orchestrator_3 via `send_message`.

## 2026-09-19T22:06:00Z
You are the Frontend UI & QA Forensic Engineer for the Resilient Integrations Contour (Milestone 3).
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_qa_3.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_qa_3/DISPATCH.md, /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md, and /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md.
Follow AGENTS.md (Ponytail Ladder: stdlib-first, 0 new dependencies in package.json and requirements.txt; Rostelecom Gen2 Light Theme).
Implement frontend/src/types.ts, api.ts, views/IntegrationsView.tsx, App.tsx, styles.css.
Implement the comprehensive test suite in backend/tests/test_integrations.py (covering RBAC, sync, deduplication, resolution, metrics showcase, 152-FZ).
Run the backend test suite to ensure all tests PASS (total tests > 55).
Run verification scripts (verify_workflow.py, verify_reports.py, verify_plan.py) to ensure all PASS.
Write your complete handoff report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_qa_3/handoff.md.
When finished, send a message to orchestrator_3 via send_message.
