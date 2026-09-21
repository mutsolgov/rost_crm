# DISPATCH — QA & Test Engineer (M3 / R4)

## Mission
Implement the comprehensive automated test suite for requirement R4 (tasks B14, B15, AC01, AC06, AC07, AC09, AC10):
- Create `backend/tests/test_interaction_patch.py` covering:
  1. `test_patch_resolves_deadlock_d02`: Card created without program and product transitions up to `document_signing`, transition to `materials_transfer` gets 422, `PATCH` assigns compatible program and product, and transition to `materials_transfer` now succeeds (200 OK, state=`materials_transfer`).
  2. `test_patch_cas_conflict`: Passing stale `expected_revision` rejects with 409 `REVISION_CONFLICT`.
  3. `test_patch_invalid_subject_combination`: Attempting to link incompatible program and product (e.g. `program-devops` with `product-test`) rejects with 422 `VALIDATION_ERROR`.
  4. `test_patch_disallows_clearing_subject_in_late_states`: In `materials_transfer` or later, clearing program or product to `None` rejects with 422.
  5. `test_patch_idempotency_and_event_sequence`: Repeat request with same `Idempotency-Key` returns identical response without duplicating events in `detail()["events"]`. Same key with different payload returns 409 `IDEMPOTENCY_CONFLICT`.
  6. `test_patch_scope_isolation_manager`: Manager B attempting to `PATCH` Manager A's card gets strict 404 `NOT_FOUND` (152-ФЗ / AC06).
  7. `test_patch_scope_isolation_after_reassignment`: When supervisor reassigns Manager A's card to Manager B, Manager A immediately gets 404 `NOT_FOUND` on `PATCH` and `GET`.
  8. `test_patch_links_contact_contract_license`: Successfully updates `contact_id`, `contract_id`, `license_id` and verifies `contact_name`, `contract_number`, `license_status` in `detail()`. Attempting to link entity from another organization returns 422.
  9. `test_catalogs_returns_contracts_licenses_contacts`: Verifies `/api/v1/catalogs` returns non-empty contacts, contracts, licenses for visible organizations.

- Ensure 100% tests in `backend/tests/test_working_slice.py` pass.
- Run `pytest backend/tests/test_working_slice.py backend/tests/test_interaction_patch.py`.

## Exclusive Write Ownership
You own exclusively:
- `backend/tests/test_interaction_patch.py`
Do NOT modify backend application code or frontend code.

## References
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_1/PROJECT.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_survey_1/handoff.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_1/handoff.md

## Verification
Execute:
`PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_working_slice.py backend/tests/test_interaction_patch.py`
Ensure all tests pass 100%.
Write handoff report to `handoff.md`.

## 2026-09-19T17:32:23Z
You are a teamwork_preview_worker acting as QA & Test Engineer for rost_crm.
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_qa_1.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You MUST read:
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_1/PROJECT.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_survey_1/handoff.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_1/handoff.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_qa_1/DISPATCH.md

Scope of changes (Milestone M3 / R4):
Create backend/tests/test_interaction_patch.py with comprehensive, rigorous tests:
1. test_patch_resolves_deadlock_d02: Prove elimination of deadlock D02 (card created without subject reaches document_signing, transition to materials_transfer fails with 422, PATCH assigns compatible program and product, transition to materials_transfer succeeds).
2. test_patch_cas_conflict: 409 REVISION_CONFLICT on stale expected_revision.
3. test_patch_invalid_subject_combination: 422 VALIDATION_ERROR on incompatible program/product.
4. test_patch_disallows_clearing_subject_in_late_states: 422 VALIDATION_ERROR on resetting subject to None in materials_transfer or later.
5. test_patch_idempotency_and_event_sequence: Replay returns identical response, single attributes_corrected event; different body with same key gives 409 IDEMPOTENCY_CONFLICT.
6. test_patch_scope_isolation_manager: Manager B gets 404 NOT_FOUND on Manager A's card.
7. test_patch_scope_isolation_after_reassignment: Manager A gets 404 NOT_FOUND on card reassigned by supervisor to Manager B.
8. test_patch_links_contact_contract_license: Successfully attaches contact, contract, license, verifies fields in detail(); rejects linking foreign organization's contact/contract with 422.
9. test_catalogs_returns_contracts_licenses_contacts: Verifies /api/v1/catalogs contains contacts, contracts, licenses for visible organizations.

Run verification:
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_working_slice.py backend/tests/test_interaction_patch.py
backend/.venv/bin/python docs/checks/verify_workflow.py
backend/.venv/bin/python docs/checks/verify_reports.py
backend/.venv/bin/python docs/checks/verify_plan.py

Ensure 100% of all tests pass with zero failures.
Write a detailed handoff report to:
/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_qa_1/handoff.md
Send a completion message back to caller with the path to your handoff.
