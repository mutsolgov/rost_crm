# DISPATCH: Backend Architecture Explorer (Survey Phase)

## Identity
- Role: Backend Architecture Explorer
- Working Directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_3_1
- Parent Orchestrator: orchestrator_3 (/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3)

## Objective
Explore the existing backend codebase to design the architecture for the Resilient Integrations Contour:
1. `backend/app/models.py` — existing models, base classes, relationships, how new models `IntegrationInbox` and `LearningMetric` should be declared.
2. `backend/app/services.py` & `backend/app/commands.py` — idempotency key management (`begin_command`, `finish_command`), database session handling, transaction management.
3. `backend/app/main.py` — endpoint structure, router patterns, error handlers, authentication and RBAC (`get_current_user`, `require_role`, `scope_clause`), prefix `/api/v1/`.
4. `backend/app/config.py` — configuration settings, environment variables for switching integration modes (mock vs live).
5. Existing test suites in `backend/tests/` (`test_working_slice.py`, `test_interaction_patch.py`, `test_attachments.py`, `test_reports_multiformat.py`, `test_import_wizard.py`) — total count of tests, testing patterns, fixtures, auth headers.
6. Verify verify_workflow.py, verify_reports.py, verify_plan.py in `docs/checks/`.

## Required Output
Write a comprehensive handoff report at `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_3_1/handoff.md` detailing:
- Exact proposed code layout for `backend/app/integrations/`:
  - `__init__.py`
  - `base.py` (BaseIntegrationAdapter, NormalizedEnvelope DTO v1.0)
  - `mock_lms.py` (MockLMSAdapter)
  - `mock_website.py` (MockWebsiteAdapter)
  - `factory.py` (get_adapter)
  - `service.py` (sync_source, reconcile_application, get_learning_metrics_summary)
- Schema definitions for `IntegrationInbox` and `LearningMetric` in `backend/app/models.py`.
- Endpoints to be added in `backend/app/main.py`:
  - `GET /api/v1/integrations/status`
  - `POST /api/v1/integrations/sync/{source}`
  - `GET /api/v1/integrations/inbox`
  - `POST /api/v1/integrations/inbox/{id}/resolve`
  - `GET /api/v1/integrations/metrics`
- Security & RBAC enforcement details (supervisor/admin allowed, manager gets 403/404, 152-FZ isolation).
- Idempotency-Key integration on mutating endpoints (`sync`, `resolve`).
- Baseline test count in backend/tests/ and requirements for `backend/tests/test_integrations.py` to achieve total tests > 55 with 100% pass.

## 2026-09-19T21:52:07Z
You are the Backend Architecture Explorer for the Resilient Integrations Contour.
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_3_1.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_3_1/DISPATCH.md and the full request in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md.
Investigate the existing backend codebase (backend/app/models.py, services.py, main.py, config.py, auth.py, commands.py, and all tests in backend/tests/).
Formulate the exact architectural blueprint for the new integrations module, models, endpoints, RBAC, idempotency, and testing strategy.
Write your complete report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_3_1/handoff.md.
When finished, send a completion message back to orchestrator_3 via send_message.
