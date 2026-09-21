## 2026-09-20T07:52:53Z
You are Frontend & Security Explorer (explorer_frontend_docs_4_1).
Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_docs_4_1
Path to ORIGINAL_REQUEST.md: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (read specifically the latest entry under ## 2026-09-20T07:50:28Z).

Your objective is to map and plan the implementation for Tasks B34 (R3 HelpPage), B17 UI (R4 Workflow Migrator UI), B33 (R5 152-FZ Compliance Matrix), and B36 (R6 ArchiMate 3.1 & C4 Docs):
1. R3: HelpPage Knowledge Base (B34, R21, AC21):
   - Inspect frontend/src/views/ReferenceViews.tsx (HelpPage), frontend/src/styles.css.
   - Plan role-based tabs: Manager (funnel 15 stages, card operations, comments, attachments up to 25MB, 10 allowed file types), Supervisor (reassigning cards, university quota, monitoring funnel, XLSX/PDF reports), Administrator (2-phase Excel import, integrations gateway & inbox reconciliation, workflow migration).
   - Plan step-by-step visual scenario cards in Rostelecom Gen2 Light palette (#7700FF, #FF4F12, #F4F5F8) with 'Important / Warning' badges.
   - Plan error code reference accordion (CAS 409 conflict, mapping 422 error, 25MB file limit, file quarantine/extension error, 404 security isolation).
2. R4: Workflow Migrator UI (B17 UI):
   - Inspect frontend/src/views/WorkflowGraphView.tsx and CatalogPage.tsx.
   - Plan modal wizard for admin area:
     * Step 1: Target version selection (v1 -> v2) & status mapping matrix table.
     * Step 2: Dry-run preview of affected cards with collision warnings and irreversibility notice.
     * Step 3: Confirmation and execution with reactive status update without page reload (SPA).
   - Plan API client additions in frontend/src/api.ts and types in frontend/src/types.ts.
3. R5: 152-FZ Compliance Matrix (B33, R27, AC27):
   - Plan docs/security/152-fz-compliance-matrix.md.
   - Trace 152-FZ, 149-FZ, FSTEC Order #117 requirements to exact code implementations in backend and frontend:
     * HTTP 404 on out-of-scope access (hiding existence of records) in services.py.
     * In-memory JWT storage (preventing XSS via localStorage/sessionStorage) in frontend.
     * Magic-bytes verification, 10 allowed extensions, 25MB limit, path traversal defense, file quarantine in services.py/routes.
     * Immutable InteractionEvent audit log with sequence numbers and payload snapshots.
     * Data depersonalization and retention regulation for archiving.
4. R6: ArchiMate 3.1 & C4 Architecture Docs (B36, R26, AC26):
   - Plan docs/architecture/rost_crm_architecture.archimate as a valid ArchiMate 3.1 XML Model Exchange File.
   - Plan docs/architecture/c4-architecture.md with Mermaid diagrams:
     * Level 1: System Context (CRM, Keycloak, External Users, LMS Zion, Laravel Site).
     * Level 2: Containers (React SPA, FastAPI Backend, SQLite/PostgreSQL DB, Secure File Storage).
     * Level 3: Components (Auth/RBAC, Workflow Engine & Migrator, Import Wizard, File Service, Reports Engine, Integrations Adapter & Inbox Engine).

Write your comprehensive findings to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_docs_4_1/report.md.
Update progress.md as you work.
When finished, send a message to orchestrator with summary of findings and report location.
