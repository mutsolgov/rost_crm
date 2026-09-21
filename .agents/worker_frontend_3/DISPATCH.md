## 2026-09-19T18:57:25Z

You are the Frontend & UX Lead for the rost_crm project (Enterprise Core & Analytics Engine package: Tasks B15, B20, B25, B16).

Your working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_3
Project workspace root: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Original user request file: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md

Read the following reference files first:
- ORIGINAL_REQUEST.md (header 2026-09-19T18:49:03Z)
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_2/PROJECT.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_survey_2/handoff.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_survey_2/handoff.md
- docs/planning/04-base-workflow.json
- docs/planning/adr/001-ui-design-system-and-full-scope.md
- AGENTS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You EXCLUSIVELY OWN these frontend files:
- frontend/src/api.ts
- frontend/src/types.ts
- frontend/src/styles.css
- frontend/src/App.tsx
- frontend/src/views/InteractionPage.tsx
- frontend/src/views/Reports.tsx
- frontend/src/views/ReferenceViews.tsx
- frontend/src/views/WorkflowGraphView.tsx (create new)

Your mission:
1. frontend/src/api.ts:
   - In raw(): do NOT set Content-Type: application/json if body is an instance of FormData.
   - Add upload<T>(path: string, formData: FormData, key?: string): Promise<T>
   - Add downloadGet(path: string, fallbackName?: string): Promise<void>
   - Support format parameter in download()
2. frontend/src/types.ts:
   - Add Attachment, ActivityQuery, ActivityResult, ActivityRow, CreatedQuery, CreatedResult, ImportPreviewRow, ImportPreviewResponse, ImportCommitResponse interfaces.
3. frontend/src/styles.css:
   - Add styling in Rostelecom Gen2 Light Theme (--rtk-color-primary: #7700FF, --rtk-color-accent: #FF4F12, --rtk-color-background: #F4F5F8, --rtk-color-card: #FFFFFF, --rtk-color-border: #E2E5EB, --rtk-color-text: #101828).
   - Add format badges (.format-pdf, .format-doc, .format-xls, .format-img, .format-archive).
   - Add drag-and-drop dropzone styles, modal stepper styles, report tabs and toolbar, and SVG diagram styles.
4. frontend/src/views/InteractionPage.tsx:
   - Add "Вложения и документы" section to the interaction card.
   - Display list of files with format badges, filename, size in KB/MB, author, upload date, and authorized download button (calling api.downloadGet).
   - Native HTML5 Drag & Drop uploader + file input button. Client-side pre-validation: reject files > 25MB and extensions not in 10-format whitelist before network call.
5. frontend/src/views/Reports.tsx:
   - 3 report modes: "Срез на дату (Snapshot)", "Динамика переходов (Activity)", "Созданные карточки (Created)".
   - Export buttons toolbar: "Скачать XLSX", "Скачать PDF", "Скачать JSON".
   - Native SVG stage distribution funnel diagram rendering counts by stage and drop-off in Gen2 colors (#7700FF, #FF4F12).
6. frontend/src/views/ReferenceViews.tsx:
   - Add "Импорт каталогов" button in CatalogPage header.
   - 3-step ImportWizardModal: Step 1 (file selection & dropzone), Step 2 (dry-run preview with counts and errors table), Step 3 (commit with progress indicator, success message, and catalog refresh).
7. frontend/src/views/WorkflowGraphView.tsx:
   - Create interactive SVG visualization of all 15 states (13 working + 2 terminal states) from 04-base-workflow.json. Highlight current stage (currentState).
8. frontend/src/App.tsx:
   - Pass api={api} and onChanged={changed} to CatalogPage.

Ponytail & Security Constraints:
- ZERO new npm packages in package.json.
- In-memory JWT only (no localStorage/sessionStorage).
- SPA responsiveness without full page reload.

Verify TypeScript syntax:
- Run node --experimental-strip-types on modified files to verify 0 syntax/type errors.

Produce a detailed handoff report in:
/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_3/handoff.md
Send a message to parent when complete with summary and path to your handoff.
