## 2026-09-20T07:51:38Z

You are the Project Orchestrator for the Gate P / Gate O Readiness Sprint (tasks B17, B31, B33, B34, B36).

### Working Directory & Context
- Your assigned working directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_4`
- Project root: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm`
- Authoritative User Request: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md` (see the latest entry `## 2026-09-20T07:50:28Z`).

### Requested Team Structure
User requested a 3-agent engineering team:
1. Архитектор процессов и производительности (Process & Performance Architect: R1 workflow migrator backend & CAS/audit, R2 load benchmark backend/benchmarks/benchmark_load.py, R7 tests).
2. Инженер UX и базы знаний (UX & Knowledge Base Engineer: R3 HelpPage role-based interactive knowledge base, R4 workflow migration UI wizard in Gen2 light theme).
3. Специалист ИБ и архитектуры (Security & Architecture Specialist: R5 152-FZ compliance matrix in docs/security/152-fz-compliance-matrix.md, R6 ArchiMate 3.1 XML and C4 Mermaid diagrams in docs/architecture/).

You may also deploy challenger/reviewer/QA as needed according to standard team workflow.

### Key Requirements to Implement & Verify
1. R1. Workflow Migration Engine (B17, R06, AC06):
   - Workflow versioning (v1: 15 base stages, v2: extended template with optimized transitions).
   - `preview_workflow_migration(db, user, from_version, to_version, status_mapping)`: validates no terminal-to-active mapping, returns affected card count, distribution, collisions.
   - `commit_workflow_migration(db, user, from_version, to_version, status_mapping, idempotency_key)`: atomic transactional migration, CAS revision update, `workflow_migrated` audit event in `InteractionEvent` preserving history/comments/attachments, Idempotency-Key support.
   - REST endpoints: `POST /api/v1/workflow/migrate/preview` (dry-run) and `POST /api/v1/workflow/migrate/commit` (supervisor/admin only).
2. R2. Load Benchmark (B31, R18, R19, AC18, AC19):
   - Standalone script `backend/benchmarks/benchmark_load.py` using stdlib / existing `asyncio` and `httpx`.
   - Emulate 50 concurrent users (40 managers, 8 supervisors, 2 admins) with 10 concurrent heavy analytical reports (Snapshot, Activity, Created) against active registry and card operations.
   - Metrics: mean, min, max, median, p95, p99, error rate.
   - Generates structured protocol `docs/benchmarks/load-test-report.md` proving R18 (<= 1.0s response time) under R19 load.
3. R3. Role-Based Interactive Knowledge Base (B34, R21, AC21):
   - Overhaul `frontend/src/views/ReferenceViews.tsx:HelpPage` into a knowledge base center.
   - Role tabs: Manager, Supervisor, Administrator.
   - Visual step-by-step scenario cards in Rostelecom Gen2 Light palette (#7700FF, #FF4F12, #F4F5F8) with 'Important / Warning' badges.
   - Error code accordion (CAS conflicts, mapping errors, 25MB limits, quarantine).
4. R4. Workflow Migrator UI (B17 UI):
   - Modal wizard in admin area (WorkflowGraphView or CatalogPage): Step 1 target version & status mapping, Step 2 preview of affected cards, Step 3 confirm and execute without full page reload (SPA).
5. R5. 152-FZ Compliance Matrix (B33, R27, AC27):
   - `docs/security/152-fz-compliance-matrix.md` tracing 152-FZ, 149-FZ, FSTEC order #117 to concrete code mechanisms (HTTP 404 scoping, in-memory JWT, file validation & path traversal protection, immutable InteractionEvent audit, data depersonalization regulation).
6. R6. ArchiMate 3.1 & C4 Architecture Documentation (B36, R26, AC26):
   - `docs/architecture/rost_crm_architecture.archimate` (valid ArchiMate 3.1 XML).
   - `docs/architecture/c4-architecture.md` with Mermaid diagrams for C4 Level 1 (Context), Level 2 (Containers), Level 3 (Components).
7. R7. Verification, Testing & DoD:
   - `backend/tests/test_workflow_migration.py` testing preview, commit, rejection of terminal-to-active mapping, history/attachment preservation, and Idempotency-Key caching.
   - All 99 existing tests + new tests PASS (`cd backend && .venv/bin/python -m pytest tests/ -v`).
   - Specification oracles PASS (`python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py`).
   - Strict Ponytail Ladder: 0 new dependencies in `backend/requirements.txt` or `frontend/package.json`.
