# DISPATCH: Frontend UI & Integration Explorer (Survey Phase)

## Identity
- Role: Frontend UI & Integration Explorer
- Working Directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_3_1
- Parent Orchestrator: orchestrator_3 (/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3)

## Objective
Explore the existing frontend codebase to design the UI components for the Resilient Integrations Contour:
1. `frontend/src/App.tsx` — current navigation, routing, tabs/views, role-based tab visibility (`supervisor`, `admin`).
2. `frontend/src/types.ts` & `frontend/src/api.ts` — API client, auth token handling (in-memory JWT), error handling, types.
3. `frontend/src/views/` (`InteractionPage.tsx`, `Reports.tsx`, `ReferenceViews.tsx`, `WorkflowGraphView.tsx`) — component patterns, modals, forms, tables, state management.
4. `frontend/src/styles.css` — Rostelecom Gen2 Light Theme tokens (`--rtk-color-primary: #7700FF`, `--rtk-color-accent: #FF4F12`, `--rtk-color-background: #F4F5F8`, `--rtk-color-text: #101828`), badge styles, card styles, buttons.
5. TypeScript build configuration and requirements (`pnpm build` must pass cleanly).

## Required Output
Write a comprehensive handoff report at `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_3_1/handoff.md` detailing:
- Navigation integration in `App.tsx`: adding «Интеграции» tab for `supervisor` and `admin` roles.
- Proposed architecture for `frontend/src/views/IntegrationsView.tsx`:
  - 1. Integration Status Section (Zion LMS & Laravel Website cards, status badges, last sync time, counters, manual "Синхронизировать сейчас" buttons).
  - 2. Reconciliation Inbox Section (filter tabs by status: pending, processed, rejected; table of applications with date, source, external id, applicant name, org, actions).
  - 3. Modal Resolution Component (choice between "Привязать к существующей организации" from catalog or "Создать новую организацию и контакт", manager assignment dropdown, confirmation button, error handling).
  - 4. Learning Metrics Showcase Section (summary cards: active cohorts, enrolled students, completed students, attendance rate; breakdown by program and organization; charts or progress bars in Rostelecom Gen2 palette).
- API client additions in `frontend/src/api.ts` and type declarations in `frontend/src/types.ts`.
- Verification plan for `pnpm build`.

## 2026-09-19T21:52:07Z
You are the Frontend UI & Integration Explorer for the Resilient Integrations Contour.
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_3_1.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_3_1/DISPATCH.md and the full request in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md.
Investigate frontend/src/App.tsx, types.ts, api.ts, views/, and styles.css.
Design the navigation tab, IntegrationsView components, status cards, reconciliation table, resolution modal, and metrics display adhering strictly to Rostelecom Gen2 Light Theme.
Write your complete report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_3_1/handoff.md.
When finished, send a completion message back to orchestrator_3 via send_message.

