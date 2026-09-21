# Context for Forensic Integrity Auditor (Milestone M4)

- Working Directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/auditor_forensic_2
- Scope: Forensic integrity audit of Enterprise Core & Analytics Engine implementation.
- Key Reference Documents:
  - /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (header 2026-09-19T18:49:03Z)
  - /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_2/PROJECT.md
  - /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_2/handoff.md
  - /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_3/handoff.md
  - AGENTS.md
- Audit Targets:
  1. Backend files: `backend/app/files.py`, `backend/app/reports_export.py`, `backend/app/importer.py`, `backend/app/services.py`, `backend/app/main.py`.
  2. Frontend files: `frontend/src/views/InteractionPage.tsx`, `frontend/src/views/Reports.tsx`, `frontend/src/views/ReferenceViews.tsx`, `frontend/src/views/WorkflowGraphView.tsx`, `frontend/src/api.ts`.
  3. Tests: `backend/tests/test_attachments.py`, `backend/tests/test_reports_multiformat.py`, `backend/tests/test_import_wizard.py`.
- Forensic Checks:
  - No dummy or facade implementations (e.g. check if XLSX generator produces real OpenXML zip packages with real XML; check if PDF generator creates real vector PDF objects; check if magic byte checks genuinely inspect bytes).
  - No hardcoded test responses or bypasses.
  - No fake verification claims.
- Verdict: CLEAN or INTEGRITY VIOLATION.
- Output: handoff.md in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/auditor_forensic_2/handoff.md
