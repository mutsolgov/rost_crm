# DISPATCH: Adversarial Challenger 1

## Mandatory Integrity Warning
DO NOT CHEAT. All stress tests must be empirical, rigorous, and genuine.

## Context & Inputs
- Authoritative Request: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md` (Section `## 2026-09-19T21:49:49Z`)
- Project Scope: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md`
- Security Rules: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md` (152-FZ, CAS, Idempotency-Key, Deduplication).

## Identity
- Role: Adversarial Challenger
- Working Directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_1_3`
- Parent Orchestrator: orchestrator_3

## Challenge Scope & Instructions
1. Stress test the deduplication engine:
   - What happens when duplicate envelopes arrive concurrently or sequentially?
   - Verify that no duplicate rows appear in `IntegrationInbox` or `LearningMetric`.
2. Stress test the reconciliation engine:
   - What happens when resolving an already-processed inbox item? (Must return 409).
   - What happens when sending conflicting payloads with the same Idempotency-Key? (Must return 409 IDEMPOTENCY_CONFLICT).
   - What happens when an unauthorized user (manager) attempts to call `/sync/lms` or `/inbox/{id}/resolve`? (Must return 403).
3. Stress test 152-FZ manager isolation:
   - Create an interaction via reconciliation assigned to `manager-a` (team `north`).
   - Try to access or update it as `manager-b` (another manager) or an out-of-scope user. (Must return 404).
4. Run stress scripts in Python, run pytest test suite.
5. Deliver handoff report at `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_1_3/handoff.md` with explicit verdict: `APPROVE` or `REQUEST_CHANGES`.
6. Send completion message to orchestrator_3 via `send_message`.

## 2026-09-19T22:13:32Z
You are Adversarial Challenger 1 for the Resilient Integrations Contour.
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_1_3.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_1_3/DISPATCH.md, /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md, and /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md.
Stress test deduplication, repeat sync operations, already-resolved 409 conflicts, Idempotency-Key replay attacks, and 152-FZ manager scope isolation.
Execute backend test suite and stress scripts.
Write your challenge report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_1_3/handoff.md with explicit verdict APPROVE or REQUEST_CHANGES.
When finished, send a message to orchestrator_3 via send_message.
