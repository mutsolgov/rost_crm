# DISPATCH — Backend Engineer (M1 / R1, R2)

## Mission
Implement requirements R1 and R2 for tasks B11, B14, B15, B18:
- `backend/app/models.py`: add `OrganizationContact`, `Contract`, `License`, `Attachment`; add FKs `contract_id`, `license_id`, `contact_id` to `Interaction`.
- `backend/app/schemas.py`: add `InteractionUpdate` (expected_revision, title, program_id, product_id, cycle_label, contact_id, contract_id, license_id); extend `InteractionCreate`.
- `backend/app/services.py`:
  - add `"interactions.edit"` to permissions defaults for manager and supervisor.
  - update `catalogs()` to include contacts, contracts, licenses for visible organizations.
  - update `interaction_dict()` to include `contact_id`, `contact_name`, `contract_id`, `contract_number`, `license_id`, `license_status`.
  - update `event_dict()` to include `changes` from payload if present.
  - implement `update_interaction(db, user, interaction_id, body, key)` with `scoped_interaction`, CAS `expected_revision`, `Idempotency-Key` (1–200 chars), `SUBJECT_REQUIRED_STATES` protection, `validate_subject`, organization consistency validation, `attributes_corrected` event with changes payload.
- `backend/app/main.py`: implement `PATCH /api/v1/interactions/{interaction_id}` route.
- `backend/app/seed.py`: add demo contacts, contracts, licenses, link to demo interactions, preserve `("manager-a", "org-1"): (True, False)` and `("manager-b", "org-2"): (True, False)`.

## Exclusive Write Ownership
You own exclusively:
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/services.py`
- `backend/app/seed.py`
- `backend/app/main.py`
Do NOT edit any frontend files.

## References
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_1/PROJECT.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_survey_1/handoff.md
- Skill: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/skills/ponytail/SKILL.md

## 2026-09-19T17:26:04Z
Execute scope of changes (Milestone M1 / R1, R2) for Backend Engineer:
- backend/app/models.py: Add OrganizationContact, Contract, License, Attachment; FKs in Interaction.
- backend/app/schemas.py: Add InteractionUpdate; extend InteractionCreate.
- backend/app/services.py: Update permissions, catalogs, interaction_dict, event_dict; implement update_interaction.
- backend/app/main.py: Add PATCH /api/v1/interactions/{interaction_id}.
- backend/app/seed.py: Add demo contacts, contracts, licenses, attach to sample interactions, preserve grants invariant.
