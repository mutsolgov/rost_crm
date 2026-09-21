## 2026-09-20T08:02:14Z
You are the Process & Performance Architect (worker_backend_4_1).
Working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_4_1
Path to ORIGINAL_REQUEST.md: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (read specifically the latest entry under ## 2026-09-20T07:50:28Z).

Read the reference reports before starting:
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_4/PROJECT.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_4_1/report.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_benchmark_4_1/report.md

Files you exclusively own:
- backend/app/workflow.py
- backend/app/services.py
- backend/app/main.py
- backend/benchmarks/benchmark_load.py
- backend/tests/test_workflow_migration.py
- docs/benchmarks/load-test-report.md

Your tasks:
1. Workflow Versioning (v1 & v2) in backend/app/workflow.py:
   - Version 1: 15 states (13 working + 2 terminal: completed, cancelled) and 29 transitions.
   - Version 2: Extended template with 7 optimized transitions (meeting_to_document_signing fast-track, materials_transfer_to_classes express launch, classes_to_completed direct finish, deployment_to_materials_transfer rework, classes_to_teacher_training rework, document_signing_to_meeting rework, cancellation transitions).
   - Export helper functions: get_workflow(version), get_states(version), get_transitions(version), allowed_transitions(state, version). Ensure backwards compatibility so existing services and tests do not break.
2. Migration Services in backend/app/services.py:
   - preview_workflow_migration(db, user, from_version, to_version, status_mapping):
     * RBAC: supervisor or administrator only (else 403 Forbidden).
     * Validate versions exist.
     * Validate status mapping: strictly reject terminal-to-active mappings with HTTP 422 APIError("VALIDATION_ERROR").
     * Query active interactions (workflow_version == from_version, state not in terminal states).
     * Calculate status_distribution_before, status_distribution_after, unmapped_statuses, collisions (N-to-1 mappings), warnings, is_valid.
   - commit_workflow_migration(db, user, from_version, to_version, status_mapping, idempotency_key):
     * RBAC: supervisor or administrator only.
     * Idempotency handling via begin_command(..., resource_id=None) and finish_command(..., resource_id=None).
     * Atomic transactional migration: update item.workflow_version = to_version, item.state = new_state, item.revision += 1 (CAS update).
     * Audit log: append_event(db, item, user, "workflow_migrated", ...) preserving all previous history, comments, and attachments.
     * If new_state is terminal, update closed_at.
3. REST Endpoints in backend/app/main.py:
   - POST /api/v1/workflow/migrate/preview
   - POST /api/v1/workflow/migrate/commit (requires Idempotency-Key header)
   - Ensure GET /api/v1/workflow accepts optional version: int = Query(1).
4. Optimization in backend/app/services.py:
   - In validate_filters: short-circuit visible_organization_ids if organization_ids is empty, preventing idle queries.
5. Automated Tests in backend/tests/test_workflow_migration.py:
   - 10+ tests: preview calculations, terminal-to-active 422 rejection, commit atomic execution, CAS revision increment, history/attachments preservation, Idempotency-Key replay, RBAC 403 on manager.
   - Run tests using .venv/bin/python -m pytest tests/ -v and ensure 100% pass (all existing 99 + new tests).
6. Load Benchmark in backend/benchmarks/benchmark_load.py:
   - Standalone script using stdlib (asyncio, time, statistics, argparse) and httpx (0 new dependencies!).
   - In-process ASGI mode and live HTTP mode.
   - Emulate 50 concurrent users (40 managers, 8 supervisors, 2 admins) + 10 concurrent analytical reports.
   - Tune AnyIO thread limiter: anyio.to_thread.current_default_thread_limiter().total_tokens = 120.
   - Compute metrics: mean, min, max, median, p90, p95, p99, error rate.
   - Run benchmark and generate docs/benchmarks/load-test-report.md proving R18 (P95 <= 1.0s) under R19 load.
7. Verify oracles:
   - python3 docs/checks/verify_workflow.py
   - python3 docs/checks/verify_reports.py
   - python3 docs/checks/verify_plan.py
