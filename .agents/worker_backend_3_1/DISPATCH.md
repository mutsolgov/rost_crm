# DISPATCH: Milestone 1 — Backend Adapter & Schema Architect

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Context & Inputs
- Authoritative Request: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md` (Section `## 2026-09-19T21:49:49Z`)
- Project Scope & Architecture: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md`
- Spec Miner Findings: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_3_1/handoff.md`
- Backend Explorer Blueprint: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_3_1/handoff.md`
- Code Rules: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md` (Ponytail Ladder: stdlib-first, 0 new dependencies in requirements.txt)

## Identity
- Role: Backend Adapter & Schema Architect
- Working Directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_1`
- Parent Orchestrator: orchestrator_3

## Exclusive File Write Ownership
You have exclusive write ownership over:
- `backend/app/models.py`
- `backend/app/config.py`
- `backend/app/integrations/__init__.py`
- `backend/app/integrations/base.py`
- `backend/app/integrations/mock_lms.py`
- `backend/app/integrations/mock_website.py`
- `backend/app/integrations/factory.py`

DO NOT modify files outside your ownership scope.

## Deliverables & Tasks
1. **`backend/app/models.py`**:
   - Add model `IntegrationInbox`:
     - `id`: `String(64)`, primary_key, default `new_id`
     - `source`: `String(32)`, index=True (`"lms"` | `"website"`)
     - `entity_type`: `String(64)`, index=True (`"learning_metric"` | `"application"`)
     - `external_id`: `String(128)`, index=True
     - `source_revision`: `String(64)`
     - `payload`: `JSON`
     - `status`: `String(32)`, default `"pending"`, index=True (`"pending"`, `"processed"`, `"quarantined"`, `"rejected"`)
     - `error_message`: `Text`, nullable=True
     - `matched_organization_id`: `ForeignKey("organizations.id")`, nullable=True, index=True
     - `matched_interaction_id`: `ForeignKey("interactions.id")`, nullable=True, index=True
     - `received_at`: `DateTime(timezone=True)`, default `utcnow`, index=True
     - `processed_at`: `DateTime(timezone=True)`, nullable=True
     - `UniqueConstraint("source", "entity_type", "external_id", "source_revision", name="uq_inbox_dedup")`
     - Indexes: `ix_inbox_source_status` on `("source", "status")`, `ix_inbox_received_at` on `("received_at")`.
   - Add model `LearningMetric`:
     - `id`: `String(64)`, primary_key, default `new_id`
     - `organization_id`: `ForeignKey("organizations.id")`, index=True
     - `program_id`: `ForeignKey("programs.id")`, index=True
     - `metric_code`: `String(64)` (`"active_cohorts"`, `"students_enrolled"`, `"students_completed"`, `"attendance_rate"`)
     - `value`: `Float` (import `Float` from sqlalchemy)
     - `unit`: `String(32)` (`"cohort"`, `"student"`, `"percent"`)
     - `as_of`: `DateTime(timezone=True)`
     - `source`: `String(32)`, default `"lms"`
     - `external_id`: `String(128)`
     - `created_at`: `DateTime(timezone=True)`, default `utcnow`
     - `UniqueConstraint("source", "external_id", name="uq_learning_metric_source_external")`
     - Indexes: `ix_metric_org_prog` on `("organization_id", "program_id")`, `ix_metric_code_as_of` on `("metric_code", "as_of")`.

2. **`backend/app/config.py`**:
   - In `Settings`, add:
     - `lms_integration_mode: str = "mock"` (allowed: `"mock"`, `"live"`)
     - `website_integration_mode: str = "mock"` (allowed: `"mock"`, `"live"`)
     - `lms_base_url: str = "https://rtkb.zion-lms.ru"`
     - `website_base_url: str = "https://it-school.rt.ru"`
   - Validate modes in `validate()` method.
   - In `get_settings()`, parse from env vars `LMS_INTEGRATION_MODE`, `WEBSITE_INTEGRATION_MODE`, `LMS_BASE_URL`, `WEBSITE_BASE_URL`.

3. **`backend/app/integrations/__init__.py`**:
   - Export `BaseIntegrationAdapter`, `NormalizedEnvelope`, `MockLMSAdapter`, `MockWebsiteAdapter`, `get_adapter`.

4. **`backend/app/integrations/base.py`**:
   - `NormalizedEnvelope` dataclass with fields:
     `schema_version: str = "1.0"`, `source: str`, `entity_type: str`, `external_id: str`, `source_revision: str`, `operation: str = "upsert"`, `effective_at: datetime`, `received_at: datetime`, `payload: dict[str, Any]`, and method `to_dict()`.
   - `BaseIntegrationAdapter` ABC with abstract methods:
     - `fetch_updates(self, since: datetime | None = None) -> list[NormalizedEnvelope]`
     - `health_check(self) -> dict[str, Any]`

5. **`backend/app/integrations/mock_lms.py`**:
   - Implement `MockLMSAdapter(BaseIntegrationAdapter)`:
     - source: `"lms"`
     - `health_check()`: returns status, mode `"mock"`, target URL.
     - `fetch_updates(since)`: generates realistic educational metrics for seeded universities (`org-1`, `org-2`, `org-3`) and programs (`program-devops`, `program-qa`) with metrics: `active_cohorts`, `students_enrolled`, `students_completed`, `attendance_rate`.

6. **`backend/app/integrations/mock_website.py`**:
   - Implement `MockWebsiteAdapter(BaseIntegrationAdapter)`:
     - source: `"website"`
     - `health_check()`: returns status, mode `"mock"`, target URL.
     - `fetch_updates(since)`: generates partnership applications with both known organizations (e.g. matching "Московский технический университет") and unknown organizations (e.g. "Казанский национальный исследовательский технический университет им. А.Н. Туполева", "Сибирский политехнический университет") with representative contacts, program, and comments.

7. **`backend/app/integrations/factory.py`**:
   - Implement `get_adapter(source: str, settings: Settings | None = None) -> BaseIntegrationAdapter`:
     - Returns `MockLMSAdapter` or `MockWebsiteAdapter` based on source and settings mode.

8. **Verification**:
   - Run the existing backend test suite (`backend/.venv/bin/pytest backend/tests/`) to ensure all 48 tests still PASS with zero regressions.
   - Run verification scripts: `python3 docs/checks/verify_workflow.py`, `verify_reports.py`, `verify_plan.py` -> PASS.
   - Document commands and results in `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_1/handoff.md`.
   - When finished, send a message to orchestrator_3 via `send_message`.

## 2026-09-19T21:55:43Z
You are the Backend Adapter & Schema Architect for the Resilient Integrations Contour (Milestone 1).
Your working directory is /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_1.
Read your instructions in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_1/DISPATCH.md, /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/ORIGINAL_REQUEST.md, and /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_3/PROJECT.md.
Follow AGENTS.md (Ponytail Ladder: stdlib-first, 0 new dependencies in requirements.txt).
Implement models in backend/app/models.py, config settings in backend/app/config.py, and the integrations package backend/app/integrations/ (base.py, mock_lms.py, mock_website.py, factory.py).
Run the backend test suite (backend/.venv/bin/pytest backend/tests/) to verify 0 regressions across all 48 tests.
Write your complete handoff report to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3_1/handoff.md.
When finished, send a message to orchestrator_3 via send_message.
