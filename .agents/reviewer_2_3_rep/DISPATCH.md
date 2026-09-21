# DISPATCH: Architecture & Quality Reviewer 2 (Replacement)

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
- Working Directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_2_3_rep`
- Parent Orchestrator: orchestrator_3

## Review Scope & Instructions
1. Independently inspect the codebase implementation and diff:
   - Backend models, adapters, service methods, and endpoints.
   - Frontend types, api, view components, and navigation.
   - Automated tests in `backend/tests/test_integrations.py`.
2. Check:
   - Ponytail compliance (no over-engineering, stdlib/native first).
   - Unified error envelope `{error: {code, message, request_id, details}}`.
   - Idempotency-Key validation and deduplication constraint behavior.
   - Lifecycle status preservation (13 working + 2 terminal).
3. Run verification commands:
   - `backend/.venv/bin/pytest backend/tests/` (must pass 100%, >= 60 tests).
   - `python3 docs/checks/verify_workflow.py` -> PASS.
   - `python3 docs/checks/verify_reports.py` -> PASS.
   - `python3 docs/checks/verify_plan.py` -> PASS.
4. Deliver your handoff report at `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_2_3_rep/handoff.md` with explicit verdict: `APPROVE` or `REQUEST_CHANGES`.
5. Send completion message to orchestrator_3 via `send_message`.

## 2026-09-19T22:18:13Z
You are Architecture & Quality Reviewer 2 for the Resilient Integrations Contour.
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_2_3_rep.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_2_3_rep/DISPATCH.md, /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md, and /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md.
Independently review code for Ponytail compliance, 152-FZ security, DTO v1.0 contracts, and error formatting.
Execute backend test suite and verification scripts.
Write your review report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/reviewer_2_3_rep/handoff.md with explicit verdict APPROVE or REQUEST_CHANGES.
When finished, send a message to orchestrator_3 via send_message.
