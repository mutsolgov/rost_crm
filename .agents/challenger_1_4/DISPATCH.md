## 2026-09-20T08:26:06Z
You are Workflow Migration Stress Challenger (challenger_1_4).
Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_1_4
Path to ORIGINAL_REQUEST.md: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (read specifically ## 2026-09-20T07:50:28Z).

Your mission is adversarial stress testing of the Workflow Migration Engine (backend/app/services.py, backend/app/main.py, backend/app/workflow.py):
- Write an adversarial stress test suite in backend/tests/test_challenger_migration_stress.py.
- Empirically test:
  1. Complex many-to-one status mapping collisions.
  2. Out-of-bounds / non-existent status mapping values.
  3. Concurrent migration attempts with the same or different Idempotency-Key.
  4. Re-migration from v2 back to v1 (or v2 to v2 rejection).
  5. Tampering with CAS revision during migration.
  6. Verification that interactions with extensive existing history, multiple comments, and multiple attachments preserve 100% of their relationships and sequence integrity post-migration.
  7. Verification that RBAC strictly rejects manager roles with 403 Forbidden.
- Run your new tests: backend/.venv/bin/python -m pytest backend/tests/test_challenger_migration_stress.py -v.
- Confirm all existing tests still pass: backend/.venv/bin/python -m pytest backend/tests/ -q.
- Issue verdict: APPROVE or REQUEST_CHANGES.
- Write handoff to .agents/challenger_1_4/handoff.md and send completion message to orchestrator.
