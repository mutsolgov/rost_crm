# DISPATCH: Specification & Fixtures Miner (Survey Phase)

## Identity
- Role: Specification & Fixture Miner
- Working Directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_3_1
- Parent Orchestrator: orchestrator_3 (/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3)

## Objective
Thoroughly mine and analyze authoritative specifications for the Resilient Integrations Contour:
1. `docs/planning/01-technical-specification.md` — Section 7.2 «Внешние источники», DTO v1.0 Normalized Envelope schema, fields, types, and constraints.
2. `docs/planning/02-development-plan.md` — Tasks B26, B27, B28, B29.
3. `docs/planning/03-acceptance-scenarios.md` — Scenarios AC12, AC13, AC29.
4. `AGENTS.md` — Standards, Ponytail Ladder (0 new dependencies), Security Invariants (152-FZ, FSTEK No.117, CAS expected_revision, Idempotency-Key).
5. `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md` (specifically section `## 2026-09-19T21:49:49Z`).

## Required Output
Write a comprehensive handoff report at `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_3_1/handoff.md` detailing:
- Exact JSON/DTO v1.0 envelope specifications (field names, types, allowed operations, schema version).
- Composite deduplication key requirements: `(source, entity_type, external_id, source_revision)`.
- Model attributes for `IntegrationInbox` and `LearningMetric` (columns, types, nullability, unique constraints, foreign keys).
- LMS Zion mock requirements: entities, metric codes (`active_cohorts`, `students_enrolled`, `students_completed`, `attendance_rate`), organizations, programs.
- Website mock requirements: application entities, fields (org name, representative, contacts, program, comments), resolution scenarios.
- Reconciliation logic & resolution actions (`link_existing`, `create_new`, `reject`).
- RBAC permissions (supervisor & admin only; manager gets 403 or 404).
- Error format `{error: {code, message, request_id, details}}`.
