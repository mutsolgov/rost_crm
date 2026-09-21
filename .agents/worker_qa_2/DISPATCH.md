## 2026-09-19T19:09:35Z

You are the QA & Forensic Test Engineer for the rost_crm project (Enterprise Core & Analytics Engine package: Task R5).

Your working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_qa_2
Project workspace root: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Original user request file: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md

Read the following reference files first:
- ORIGINAL_REQUEST.md (header 2026-09-19T18:49:03Z)
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_2/PROJECT.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_2/handoff.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_3/handoff.md
- AGENTS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your mission:
1. Review and verify the backend test suite:
   - backend/tests/test_attachments.py (verify all 10 whitelist formats, magic byte checking, 25MB limit 413, path traversal sanitization, 152-FZ scope 404, SHA-256).
   - backend/tests/test_reports_multiformat.py (verify OpenXML XLSX signature PK\x03\x04, vector PDF signature %PDF-1.4, JSON export, activity report owner_at_event historical resolution, created report).
   - backend/tests/test_import_wizard.py (verify dry-run preview with 0 DB mutations, row-level validation errors, transactional commit, Idempotency-Key conflict).
   - backend/tests/test_working_slice.py & test_interaction_patch.py.
2. If any critical edge case from spec miner handoff (/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_survey_2/handoff.md) is missing or needs further coverage, add it to the test files.
3. Run the full backend test suite:
   PYTHONPATH=. /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/bin/pytest backend/tests/
   Ensure >40 total tests pass (100% PASS rate).
4. Run the specification and plan oracles:
   python3 docs/checks/verify_workflow.py
   python3 docs/checks/verify_reports.py
   python3 docs/checks/verify_plan.py
   Ensure all three pass.

Produce a detailed handoff report in:
/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_qa_2/handoff.md
Send a message to parent when complete with summary and path to your handoff.
