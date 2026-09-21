## 2026-09-20T08:02:08Z
You are the UX & Knowledge Base Engineer (worker_frontend_4_1).
Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_4_1
Path to ORIGINAL_REQUEST.md: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (read specifically the latest entry under ## 2026-09-20T07:50:28Z).

Read the reference reports before starting:
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_4/PROJECT.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_docs_4_1/report.md

Files you exclusively own:
- frontend/src/types.ts
- frontend/src/api.ts
- frontend/src/views/ReferenceViews.tsx
- frontend/src/views/CatalogPage.tsx
- frontend/src/styles.css

Your tasks:
1. Extend frontend/src/types.ts & frontend/src/api.ts:
   - Add types for WorkflowMigrationPreview, WorkflowMigrationResult, StatusCollision, etc.
   - Add api client methods:
     * previewWorkflowMigration(token, body) -> POST /api/v1/workflow/migrate/preview
     * commitWorkflowMigration(token, body, idempotencyKey) -> POST /api/v1/workflow/migrate/commit
2. Overhaul HelpPage in frontend/src/views/ReferenceViews.tsx (Task B34, R21, AC21):
   - Replace the stub HelpPage with a full-featured Knowledge Base Center.
   - Role tabs:
     * Менеджер (funnel 15 stages, card workflow, comments, attachments up to 25MB and 10 formats, deadlock D02 avoidance via program/product selection).
     * Руководитель (university quota management, reassigning cards, funnel monitoring, 3 report types: Snapshot, Activity, Created in XLSX/PDF).
     * Администратор (2-phase Excel import wizard, integrations gateway & reconciliation inbox, workflow migrations v1->v2).
   - Visual step-by-step scenario cards in Rostelecom Gen2 Light palette (#7700FF, #FF4F12, #F4F5F8) with 'Важно / Внимание' badges.
   - Error code reference accordion:
     * 409 Conflict (CAS revision mismatch)
     * 422 Unprocessable Entity (mapping terminal to active, invalid transition)
     * 413 Payload Too Large (file exceeds 25 MB limit)
     * 422 File Quarantine (unsupported extension or executable magic bytes)
     * 404 Not Found (152-FZ security isolation / record existence hiding)
   - Preserve user input without form wipes.
3. Workflow Migrator UI Modal (Task B17 UI, R06):
   - Implement WorkflowMigratorModal in ReferenceViews.tsx or CatalogPage.tsx:
     * Step 1: Target version selection (v1 -> v2) & status mapping matrix with inline validation blocking terminal-to-active mappings.
     * Step 2: Dry-run preview showing affected card count, before/after distribution, collision warnings, and irreversibility warning.
     * Step 3: Confirmation and commit execution with Idempotency-Key (crypto.randomUUID()) and reactive UI update without page reload (SPA).
   - Integrate modal launcher button in CatalogPage.tsx for supervisor/administrator roles.
4. CSS styling in frontend/src/styles.css:
   - Style the knowledge base tabs, scenario cards, accordion, and migration wizard using existing Gen2 CSS variables (--rtk-color-primary: #7700FF, --rtk-color-accent: #FF4F12, --rtk-color-background: #F4F5F8, etc.).
5. Strict Ponytail Ladder: 0 new npm packages in package.json.
