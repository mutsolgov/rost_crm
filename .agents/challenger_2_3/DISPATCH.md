# DISPATCH: Adversarial Challenger 2

## Mandatory Integrity Warning
DO NOT CHEAT. All stress tests must be empirical, rigorous, and genuine.

## Context & Inputs
- Authoritative Request: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md` (Section `## 2026-09-19T21:49:49Z`)
- Project Scope: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md`
- Security Rules: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md` (152-FZ, CAS, Idempotency-Key, Deduplication).

## Identity
- Role: Adversarial Challenger
- Working Directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_3`
- Parent Orchestrator: orchestrator_3

## Challenge Scope & Instructions
1. Stress test input validation and edge cases:
   - Invalid or malformed payloads to `/inbox/{id}/resolve`.
   - Unknown action names (e.g. action="drop_db" or action="unknown"). Must return 422 or 400.
   - Idempotency-Key length validation (> 200 chars must be rejected).
   - Empty/blank names or invalid organization IDs.
2. Stress test Educational Metrics Showcase:
   - Filtering by non-existent organization_id or program_id (should return clean 0 totals, not 500 crash).
   - Verify manager scoping (line manager should only see metrics for organizations they have access to).
3. Run backend pytest test suite and verification scripts.
4. Deliver handoff report at `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_3/handoff.md` with explicit verdict: `APPROVE` or `REQUEST_CHANGES`.
5. Send completion message to orchestrator_3 via `send_message`.

## 2026-09-20T01:13:32+03:00
You are Adversarial Challenger 2 for the Resilient Integrations Contour.
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_3.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_3/DISPATCH.md, /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md, and /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md.
Stress test invalid payloads, unknown reconciliation actions, Idempotency-Key length limits, metrics filtering edge cases, and manager scoping.
Execute backend test suite and stress scripts.
Write your challenge report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_3/handoff.md with explicit verdict APPROVE or REQUEST_CHANGES.
When finished, send a message to orchestrator_3 via send_message.
