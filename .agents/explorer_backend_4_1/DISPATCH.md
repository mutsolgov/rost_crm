## 2026-09-20T07:52:53Z
You are Backend Workflow Explorer (explorer_backend_4_1).
Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_4_1
Path to ORIGINAL_REQUEST.md: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (read specifically the latest entry under ## 2026-09-20T07:50:28Z).

Your objective is to map and plan the implementation for Task B17 (R1 Workflow Migration Engine & R7 Tests):
1. Investigate existing workflow models, transitions, and state management in:
   - backend/app/models.py (Interaction, InteractionEvent, InteractionStatus, statuses, revisions)
   - backend/app/services.py (workflow definitions, transitions, CAS updates, audit events, command idempotency)
   - backend/app/main.py (existing workflow routes)
   - docs/planning/04-base-workflow.json (13 working + 2 terminal stages)
2. Define how Workflow Versioning should be represented:
   - Version 1: 15 base stages as defined in 04-base-workflow.json.
   - Version 2: Extended template with optimized transitions (specify what states/transitions exist in v2).
3. Plan the preview service:
   - preview_workflow_migration(db, user, from_version, to_version, status_mapping)
   - Validation: reject terminal-to-active status mapping with 422, detect unmapped statuses, detect status collisions.
   - Return payload: affected_interactions_count, status_distribution_before, status_distribution_after, warnings/collisions, is_valid.
4. Plan the commit service:
   - commit_workflow_migration(db, user, from_version, to_version, status_mapping, idempotency_key)
   - Atomic transactional update across all matching interactions.
   - Increment interaction revisions (CAS safety).
   - Log InteractionEvent with type="workflow_migrated" preserving existing history, comments, and attachments.
   - Idempotency-Key support via begin_command / finish_command.
5. Plan REST endpoints in backend/app/main.py:
   - POST /api/v1/workflow/migrate/preview
   - POST /api/v1/workflow/migrate/commit
   - Role permissions: supervisor and administrator only. Manager should get 403 Forbidden.
6. Plan test cases for backend/tests/test_workflow_migration.py:
   - Preview calculations and status distribution
   - Rejection of terminal-to-active mapping (HTTP 422)
   - Commit atomic execution and revision increments
   - Preservation of interaction history, comments, attachments
   - Idempotency-Key duplicate prevention
   - RBAC permissions (supervisor/admin allowed, manager forbidden).
   - Compatibility with existing 99 tests.

Write your comprehensive findings to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_4_1/report.md.
Update progress.md as you work.
When finished, send a message to orchestrator with summary of findings and report location.
