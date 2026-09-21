# DISPATCH: Architecture & Quality Reviewer 1

## Mandatory Integrity Warning
DO NOT CHEAT. All verifications must be genuine. A teamwork_preview_auditor will independently verify the project.

## Context & Inputs
- Authoritative Request: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md` (Section `## 2026-09-19T21:49:49Z`)
- Project Scope & Architecture: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md`
- Code Rules: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md` (Ponytail Ladder: stdlib-first, 0 new dependencies; 152-FZ security invariants; Rostelecom Gen2 theme).
- Milestone Handoffs:
  - M1: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_1/handoff.md`
  - M2: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_2/handoff.md`
  - M3: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_qa_3/handoff.md`

## Identity
- Role: Architecture & Quality Reviewer
- Working Directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_1_3`
- Parent Orchestrator: orchestrator_3

## Review Scope & Instructions
1. Inspect the codebase diff and implementation:
   - `backend/app/models.py` (`IntegrationInbox`, `LearningMetric`)
   - `backend/app/config.py`
   - `backend/app/integrations/` (`base.py`, `mock_lms.py`, `mock_website.py`, `factory.py`, `service.py`, `__init__.py`)
   - `backend/app/services.py` (`permissions()`)
   - `backend/app/main.py` (5 endpoints under `/api/v1/integrations/`)
   - `backend/tests/test_integrations.py`
   - `frontend/src/types.ts`, `api.ts`, `views/IntegrationsView.tsx`, `App.tsx`, `styles.css`.
2. Verify:
   - Correctness of normalized DTO v1.0 schema and deduplication key `(source, entity_type, external_id, source_revision)`.
   - Security: 152-FZ scope isolation (manager receives 403 on integration management; manager cannot access cards outside their scope).
   - Idempotency-Key support and CAS.
   - Zero new dependencies in `requirements.txt` and `package.json`.
3. Execute:
   - `backend/.venv/bin/pytest backend/tests/` (must pass 100%, >= 60 tests).
   - `python3 docs/checks/verify_workflow.py` -> PASS.
   - `python3 docs/checks/verify_reports.py` -> PASS.
   - `python3 docs/checks/verify_plan.py` -> PASS.
4. Deliver your handoff report at `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_1_3/handoff.md` with explicit verdict: `APPROVE` or `REQUEST_CHANGES`.
5. Send completion message to orchestrator_3 via `send_message`.

## 2026-09-20T01:13:32Z
You are Architecture & Quality Reviewer 1 for the Resilient Integrations Contour.
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_1_3.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_1_3/DISPATCH.md, /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md, and /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md.
Review all implementation code (backend models, adapters, service, endpoints, tests, and frontend views).
Execute backend test suite and verification scripts.
Write your review report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_1_3/handoff.md with explicit verdict APPROVE or REQUEST_CHANGES.
When finished, send a message to orchestrator_3 via send_message.
