# Architectural Blueprint & Handoff Report: Resilient Integrations Contour (B26–B29)

## 1. Observation

Direct observations from examining the existing repository codebase and test suite:

1. **Test Baseline and Environment**:
   - Running `backend/.venv/bin/pytest backend/tests/ -q` produced:
     ```
     ................................................                         [100%]
     48 passed, 2 warnings in 15.13s
     ```
     Exact baseline: **48 passed tests** across 5 test suites (`test_working_slice.py` [12], `test_interaction_patch.py` [12], `test_attachments.py` [11], `test_reports_multiformat.py` [6], `test_import_wizard.py` [7]).
   - Verification scripts in `docs/checks/` (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) were executed and all produced `PASS`:
     ```
     PASS: 13 working states, 2 terminal states, 29 transitions, 1 initial state.
     VERIFIED 6 interactions, 23 canonical events, 3 delivery examples, 12 exact report cases.
     PASS: 40 tasks, no dependency cycles, all stage totals match.
     PASS: R01-R29 mapped to existing tasks and 30 acceptance scenarios.
     ```

2. **Idempotency & Command Execution (`backend/app/services.py` & `backend/app/models.py`)**:
   - `commands.py` does not exist as an independent module.
   - Command idempotency logic is implemented in `backend/app/services.py:179-210`:
     - `begin_command(db, user, operation, key, payload)` computes SHA-256 of JSON payload with canonical sorting (`json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))`).
     - Checks `CommandResult` model (`backend/app/models.py:167-178`), which enforces `UniqueConstraint("user_id", "operation", "key", name="uq_command_key")`.
     - Validates `Idempotency-Key` length ($\le 200$ chars) and rejects mismatches with `409 IDEMPOTENCY_CONFLICT`.
     - `finish_command(db, saved, response, resource_id)` records the response, sets `resource_id`, and executes `db.commit()`.
     - When `saved.resource_id` is `None` (as in `importer.py:414`), `scoped_interaction` is not triggered, allowing non-interaction-bound operations.

3. **Models Base and Existing Declarations (`backend/app/models.py`)**:
   - Base declarative class is `Base` (`from .db import Base`).
   - Standard ID and timestamp helpers: `new_id()` returns `str(uuid4())`, `utcnow()` returns `datetime.now(timezone.utc)`.
   - Existing core models: `User`, `Organization`, `OrganizationAccess`, `Direction`, `Program`, `Product`, `ProgramProduct`, `OrganizationContact`, `Contract`, `License`, `Interaction`, `Attachment`, `InteractionEvent`, `Comment`, `CommandResult`.
   - No models currently exist for `IntegrationInbox` or `LearningMetric`.

4. **Authentication & RBAC (`backend/app/auth.py` & `backend/app/services.py`)**:
   - `auth.py` provides `current_user(db, authorization, x_demo_user, config) -> User`.
   - In demo mode, users are authenticated via `X-Demo-User` header.
   - Seeded users (`backend/app/seed.py:28-33`):
     - `manager-a` (role: `"manager"`, team: `"north"`)
     - `manager-b` (role: `"manager"`, team: `"north"`)
     - `supervisor` (role: `"supervisor"`, team: `"north"`)
     - `administrator` (role: `"administrator"`, team: `None`)
   - `services.py:25-39` defines `permissions(user)` and `require_permission(user, name)`:
     - `manager` has access to personal interactions and reading reports.
     - `supervisor` has access to team interactions, assigning, reading reports, creating organizations.
     - `administrator` has system administration and organization creation rights.
   - `services.py:41-54` defines `scope_clause(user)` and `scoped_interaction(db, user, interaction_id)`:
     - 152-FZ isolation: Manager gets `404 Not Found` when trying to access a card belonging to another manager.

5. **Configuration (`backend/app/config.py`)**:
   - `Settings` dataclass (lines 6-26) with `get_settings()` (lines 28-47).
   - Currently handles `database_url`, `app_env`, `auth_mode`, OIDC parameters, and `storage_dir`.
   - Does not yet expose integration mode toggles (`lms_integration_mode`, `website_integration_mode`).

6. **Application Router (`backend/app/main.py`)**:
   - Uses `FastAPI` instance created in `create_app(settings)`.
   - Endpoints are directly mounted on `app` with `/api/v1/` prefix and tags (`tags=["interactions"]`, `tags=["reports"]`, `tags=["imports"]`).
   - Consistent error handling via `install_error_handlers(app)` (`backend/app/errors.py`), producing `{"error": {"code": ..., "message": ..., "request_id": ..., "details": ...}}`.

---

## 2. Logic Chain

1. **From B26-B29 and TS 7.2 Requirements to Architecture**:
   - Requirement R09/R11/R12 requires data envelopes from external systems to be ingested into an inbox before domain processing, guaranteeing idempotency, deduplication, and replay resilience.
   - Requirement B26/AC13 dictates that external packets with composite key `(source, entity_type, external_id, source_revision)` must be strictly deduplicated at the database constraint level.
   - Therefore, `IntegrationInbox` in `models.py` must define a composite `UniqueConstraint("source", "entity_type", "external_id", "source_revision", name="uq_inbox_dedup")`.

2. **From Pluggable Adapter Requirement (B27, B28, R13, R20) to Module Design**:
   - Both Zion LMS (`rtkb.zion-lms.ru`) and the Laravel website must be pluggable: operable in mock/stub mode during testing/demo, with zero external network calls, and switchable to live mode via config.
   - Following Ponytail principles (stdlib first, 0 new pip dependencies, no unnecessary event buses or complex factories):
     - An abstract base class `BaseIntegrationAdapter` in `backend/app/integrations/base.py` with two methods: `fetch_updates(since)` and `health_check()`.
     - `NormalizedEnvelope` DTO v1.0 standardizing external data to the exact schema specified in TS 7.2.
     - `MockLMSAdapter` in `mock_lms.py` delivering deterministic educational metrics for seeded universities (`org-1`, `org-2`, `org-3`) and programs (`program-devops`, `program-qa`).
     - `MockWebsiteAdapter` in `mock_website.py` delivering incoming partnership applications with both known organizations (exact name match) and unknown organizations requiring manual reconciliation.
     - `factory.py:get_adapter(source)` selecting the adapter instance based on `Settings`.

3. **From Reconciliation Queue and 152-FZ Invariants to Service Logic**:
   - Automatic processing in `sync_source()`:
     - Learning metrics are processed automatically: resolved against `Organization` and `Program`, upserted into `LearningMetric`, and inbox item marked as `processed`.
     - Applications for known organizations can be matched (`matched_organization_id = org.id`), but still require operator confirmation or stay pending. Applications for unknown organizations remain `status="pending"`.
   - Resolution in `reconcile_application()`:
     - Three discrete actions: `link_existing`, `create_new`, `reject`.
     - Must be protected by `Idempotency-Key` using `begin_command` / `finish_command` with operation `integrations.resolve:{inbox_id}`.
     - When creating an `Interaction`, owner must be validated via `allowed_owner(db, user, owner_id)`.
     - 152-FZ isolation is maintained because the resulting `Interaction` receives `team_id = supervisor.team_id`, so other managers outside the team/owner cannot access it (returning 404).

4. **From RBAC Specification to Security Layer**:
   - Dispatches and acceptance scenarios mandate:
     - Only `supervisor` and `administrator` may view integration status, trigger sync, view inbox, resolve applications, or access metric showcases.
     - `manager` calling these endpoints must be rejected with `403 Forbidden` (`APIError("FORBIDDEN", ...)`).
   - We reuse the established `require_permission(user, "integrations.manage")` by adding `"integrations.manage"` to `supervisor` and `administrator` defaults in `services.py:permissions()`.

5. **From Target Test Count (> 55) to QA Strategy**:
   - Baseline is 48 passing tests.
   - Adding 10 dedicated integration tests in `backend/tests/test_integrations.py` will bring the total to 58 tests ($> 55$), covering:
     - Adapter health and status API
     - LMS sync and `LearningMetric` ingestion
     - Deduplication and idempotency on repeated sync
     - Website application ingestion and `pending` inbox status
     - `resolve` with `link_existing` (creating interaction)
     - `resolve` with `create_new` (creating org, contact, interaction)
     - `resolve` with `reject`
     - Idempotency replay and conflict on `resolve`
     - Metrics summary aggregation
     - RBAC enforcement (manager 403 vs supervisor/admin 200)
     - 152-FZ isolation on cards created via integration

---

## 3. Caveats

1. **No External Network Calls**:
   - `MockLMSAdapter` and `MockWebsiteAdapter` must operate completely in-memory with static/deterministic fixture generators. No actual HTTP calls to `rtkb.zion-lms.ru` or external domains during tests or demo mode.
2. **Database Engine Differences**:
   - Production uses PostgreSQL (`postgresql+psycopg`), while test suite uses SQLite in-memory / temporary file.
   - Model definitions must use standard SQLAlchemy types (`Float`, `String`, `JSON`, `DateTime(timezone=True)`) compatible with both engines.
3. **Pydantic Model Extra Fields**:
   - Existing schemas inherit from `Body(BaseModel)` with `ConfigDict(extra="forbid", str_strip_whitespace=True)`. New schema models for inbox resolution must follow this exact convention.

---

## 4. Conclusion & Architectural Blueprint

### 4.1. Models Definition (`backend/app/models.py`)

Add the following two models to `backend/app/models.py` (import `Float` from `sqlalchemy`):

```python
class IntegrationInbox(Base):
    __tablename__ = "integration_inbox"
    __table_args__ = (
        UniqueConstraint("source", "entity_type", "external_id", "source_revision", name="uq_inbox_dedup"),
        Index("ix_inbox_source_status", "source", "status"),
        Index("ix_inbox_received_at", "received_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(32))  # "lms" | "website"
    entity_type: Mapped[str] = mapped_column(String(64))  # "learning_metric" | "application"
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    source_revision: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # "pending", "processed", "quarantined", "rejected"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=True)
    matched_interaction_id: Mapped[str | None] = mapped_column(ForeignKey("interactions.id"), index=True, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearningMetric(Base):
    __tablename__ = "learning_metrics"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_learning_metric_source_external"),
        Index("ix_metric_org_prog", "organization_id", "program_id"),
        Index("ix_metric_code_as_of", "metric_code", "as_of"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), index=True)
    metric_code: Mapped[str] = mapped_column(String(64))  # "active_cohorts", "students_enrolled", "students_completed", "attendance_rate"
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))  # "cohort", "student", "percent"
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32), default="lms")
    external_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

### 4.2. Configuration Additions (`backend/app/config.py`)

Extend `Settings`:
```python
@dataclass(frozen=True)
class Settings:
    ...
    lms_integration_mode: str = "mock"       # "mock" | "live"
    website_integration_mode: str = "mock"   # "mock" | "live"
    lms_base_url: str = "https://rtkb.zion-lms.ru"
    website_base_url: str = "https://it-school.rt.ru"

    def validate(self):
        ...
        if self.lms_integration_mode not in {"mock", "live"}:
            raise RuntimeError("LMS_INTEGRATION_MODE must be mock or live")
        if self.website_integration_mode not in {"mock", "live"}:
            raise RuntimeError("WEBSITE_INTEGRATION_MODE must be mock or live")
```

Extend `get_settings()` to read `LMS_INTEGRATION_MODE`, `WEBSITE_INTEGRATION_MODE`, `LMS_BASE_URL`, `WEBSITE_BASE_URL`.

### 4.3. RBAC Additions (`backend/app/services.py`)

In `permissions(user)` (`services.py:25-33`), add `"integrations.manage"` to `supervisor` and `administrator`:
```python
def permissions(user):
    defaults = {
        "manager": {"interactions.create", "interactions.transition", "interactions.comment",
                    "interactions.edit", "reports.read"},
        "supervisor": {"interactions.create", "interactions.transition", "interactions.comment",
                       "interactions.assign", "interactions.edit", "reports.read", "organizations.create",
                       "integrations.manage"},
        "administrator": {"workflow.manage", "users.manage", "organizations.create", "reports.read",
                          "integrations.manage"},
    }
    return sorted(defaults.get(user.role, set()) | set(user.permissions or []))
```

### 4.4. Module `backend/app/integrations/` Architecture

Create package directory `backend/app/integrations/` with 6 files:

```
backend/app/integrations/
├── __init__.py
├── base.py
├── mock_lms.py
├── mock_website.py
├── factory.py
└── service.py
```

#### 1. `backend/app/integrations/base.py`:
- `NormalizedEnvelope`:
  ```python
  from dataclasses import dataclass
  from datetime import datetime
  from typing import Any

  @dataclass
  class NormalizedEnvelope:
      schema_version: str        # "1.0"
      source: str                # "lms" | "website"
      entity_type: str           # "learning_metric" | "application"
      external_id: str
      source_revision: str
      operation: str             # "upsert"
      effective_at: datetime
      received_at: datetime
      payload: dict[str, Any]

      def to_dict(self) -> dict[str, Any]:
          return {
              "schema_version": self.schema_version,
              "source": self.source,
              "entity_type": self.entity_type,
              "external_id": self.external_id,
              "source_revision": self.source_revision,
              "operation": self.operation,
              "effective_at": self.effective_at.isoformat(),
              "received_at": self.received_at.isoformat(),
              "payload": self.payload,
          }
  ```
- `BaseIntegrationAdapter(ABC)`:
  ```python
  from abc import ABC, abstractmethod

  class BaseIntegrationAdapter(ABC):
      @abstractmethod
      def fetch_updates(self, since: datetime | None = None) -> list[NormalizedEnvelope]:
          pass

      @abstractmethod
      def health_check(self) -> dict[str, Any]:
          pass
  ```

#### 2. `backend/app/integrations/mock_lms.py`:
- Implements `MockLMSAdapter(BaseIntegrationAdapter)`:
  - Generates realistic learning metrics for organizations (`org-1`, `org-2`, `org-3`) and programs (`program-devops`, `program-qa`).
  - Metrics generated:
    - `active_cohorts`: 3 (org-1), 2 (org-2), 1 (org-3)
    - `students_enrolled`: 65.0 (org-1), 42.0 (org-2), 24.0 (org-3)
    - `students_completed`: 58.0 (org-1), 36.0 (org-2), 20.0 (org-3)
    - `attendance_rate`: 92.4 (org-1), 88.5 (org-2), 85.0 (org-3)
  - Canonical envelope matching TS 7.2 specification.
  - Deterministic external IDs (e.g. `lms-metric-org-1-devops-cohorts-v1`) ensuring stable hash and deduplication.
  - `health_check()` returning `{"status": "ok", "mode": "mock", "source": "lms", "endpoint": "https://rtkb.zion-lms.ru/", "latency_ms": 14}`.

#### 3. `backend/app/integrations/mock_website.py`:
- Implements `MockWebsiteAdapter(BaseIntegrationAdapter)`:
  - Generates realistic university admission/partnership applications:
    1. Known org: `"Московский технический университет"` (matches `org-1`), applicant: `"Иванов Иван Иванович"`, program: `"program-devops"`.
    2. Known org: `"Северный университет прикладных наук"` (matches `org-2`), applicant: `"Петров Петр Петрович"`, program: `"program-qa"`.
    3. Unknown org: `"Сибирский государственный университет телекоммуникаций и информатики"`, applicant: `"Сидоров Алексей Владимирович"`, program: `"program-devops"`, comments: `"Заявка на партнерство с сайта"`.
    4. Unknown org: `"Уральский политехнический институт"`, applicant: `"Кузнецова Ольга Николаевна"`, program: `"program-qa"`, comments: `"Пилотная группа QA"`.
  - Deterministic external IDs (`web-app-001`, `web-app-002`, etc.) and `source_revision="1"`.
  - `health_check()` returning `{"status": "ok", "mode": "mock", "source": "website", "endpoint": "https://it-school.rt.ru/", "latency_ms": 18}`.

#### 4. `backend/app/integrations/factory.py`:
- `get_adapter(source: str, settings: Settings | None = None) -> BaseIntegrationAdapter`:
  - If `source == "lms"`: returns `MockLMSAdapter()` (or raises 503 `SOURCE_UNAVAILABLE` if in unsupported mode).
  - If `source == "website"`: returns `MockWebsiteAdapter()`.
  - Otherwise raises `APIError("VALIDATION_ERROR", f"Неизвестный источник интеграции: '{source}'. Допустимо: 'lms', 'website'.", 400)`.

#### 5. `backend/app/integrations/service.py`:
- Core business operations:
  - `get_integrations_status(db: Session, settings: Settings) -> dict`:
    - Checks adapter health for both `lms` and `website`.
    - Queries `IntegrationInbox` for: `total_items`, `pending_count`, `processed_count`, `quarantined_count`, `rejected_count`, `last_synced_at`.
  - `sync_source(db: Session, user: User, source: str, idempotency_key: str | None = None, settings: Settings | None = None) -> dict`:
    - RBAC check: `require_permission(user, "integrations.manage")`.
    - `saved, replay = begin_command(db, user, f"integrations.sync:{source}", idempotency_key, {"source": source})`.
    - If replay, returns replay immediately.
    - Gets adapter and fetches envelopes.
    - Loops over envelopes:
      - Checks `select(IntegrationInbox).where(source, entity_type, external_id, source_revision)`.
      - If exists, increments `duplicates_count`.
      - If new, instantiates `IntegrationInbox(...)`.
      - For `learning_metric`: matches org & program, creates/updates `LearningMetric` via CAS/upsert, marks inbox `processed`.
      - For `application`: looks up `Organization` by name. If found, sets `matched_organization_id = org.id`, remains `pending`. If not found, `matched_organization_id = None`, remains `pending`.
      - Adds inbox item, flushes.
    - Returns summary via `finish_command(db, saved, summary, None)`.
  - `list_inbox(db: Session, user: User, source: str | None, status: str | None, page: int = 1, page_size: int = 50) -> dict`:
    - RBAC check: `require_permission(user, "integrations.manage")`.
    - Queries inbox with filters, joined org name, pagination.
  - `reconcile_application(db: Session, user: User, inbox_id: str, payload: dict, idempotency_key: str | None = None) -> dict`:
    - RBAC check: `require_permission(user, "integrations.manage")`.
    - `saved, replay = begin_command(db, user, f"integrations.resolve:{inbox_id}", idempotency_key, payload)`.
    - If replay, returns replay immediately.
    - Gets `inbox = db.get(IntegrationInbox, inbox_id)`. If missing -> 404.
    - If `inbox.status != "pending"` -> 422 `VALIDATION_ERROR`.
    - `action = payload.get("action")`:
      - `"reject"`: updates status to `rejected`, sets `error_message = payload.get("reason")`.
      - `"link_existing"`: validates `organization_id`, creates contact if needed, optionally creates `Interaction` using `allowed_owner(db, user, owner_id)`.
      - `"create_new"`: creates `Organization`, grants access via `OrganizationAccess`, creates contact, optionally creates `Interaction`.
    - Updates inbox: `status = "processed"`, `processed_at = utcnow()`, `matched_organization_id`, `matched_interaction_id`.
    - Returns result via `finish_command(db, saved, result, interaction.id if interaction else None)`.
  - `get_learning_metrics_summary(db: Session, user: User, organization_id: str | None = None, program_id: str | None = None) -> dict`:
    - RBAC check: `require_permission(user, "integrations.manage")`.
    - Aggregates metrics: total enrolled students, completed students, active cohorts, average completion/attendance rate, broken down by program and organization.

#### 6. `backend/app/integrations/__init__.py`:
- Clean export of all public adapters, DTOs, and service functions.

### 4.5. Request Schemas (`backend/app/schemas.py`)

Add to `backend/app/schemas.py`:
```python
class InboxResolveRequest(Body):
    action: Literal["link_existing", "create_new", "reject"]
    organization_id: str | None = None
    organization_name: str | None = None
    organization_type: Literal["university", "school", "other"] = "university"
    program_id: str | None = None
    product_id: str | None = None
    owner_id: str | None = None
    create_interaction: bool = True
    reason: str | None = None
```

### 4.6. Endpoints in `backend/app/main.py`

Mount the following 5 endpoints in `create_app()`:

1. `GET /api/v1/integrations/status`:
   ```python
   @app.get("/api/v1/integrations/status", tags=["integrations"])
   def get_status(db: Session = Depends(get_db), user: User = Depends(current_user)):
       return get_integrations_status(db, config)
   ```

2. `POST /api/v1/integrations/sync/{source}`:
   ```python
   @app.post("/api/v1/integrations/sync/{source}", tags=["integrations"])
   def post_sync(
       source: str,
       idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
       db: Session = Depends(get_db),
       user: User = Depends(current_user),
   ):
       return sync_source(db, user, source, idempotency_key, config)
   ```

3. `GET /api/v1/integrations/inbox`:
   ```python
   @app.get("/api/v1/integrations/inbox", tags=["integrations"])
   def get_inbox(
       source: str | None = None,
       status: str | None = None,
       page: int = Query(1, ge=1),
       page_size: int = Query(50, ge=1, le=100),
       db: Session = Depends(get_db),
       user: User = Depends(current_user),
   ):
       return list_inbox(db, user, source, status, page, page_size)
   ```

4. `POST /api/v1/integrations/inbox/{inbox_id}/resolve`:
   ```python
   @app.post("/api/v1/integrations/inbox/{inbox_id}/resolve", tags=["integrations"])
   def resolve_inbox(
       inbox_id: str,
       body: InboxResolveRequest,
       idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
       db: Session = Depends(get_db),
       user: User = Depends(current_user),
   ):
       return reconcile_application(db, user, inbox_id, body.model_dump(), idempotency_key)
   ```

5. `GET /api/v1/integrations/metrics`:
   ```python
   @app.get("/api/v1/integrations/metrics", tags=["integrations"])
   def get_metrics(
       organization_id: str | None = None,
       program_id: str | None = None,
       db: Session = Depends(get_db),
       user: User = Depends(current_user),
   ):
       return get_learning_metrics_summary(db, user, organization_id, program_id)
   ```

### 4.7. Testing Strategy (`backend/tests/test_integrations.py`)

The test suite must include 10 comprehensive tests:
1. `test_integrations_status`: Verifies status endpoint returns 200 for supervisor/admin and reports both LMS and Website adapters in mock mode.
2. `test_sync_lms_populates_learning_metrics`: Verifies sync creates `IntegrationInbox` items with `status="processed"` and creates `LearningMetric` records in DB.
3. `test_sync_deduplication_and_idempotency`: Verifies that a second sync run (or replay with the same `Idempotency-Key`) does not duplicate inbox or metric records.
4. `test_sync_website_populates_inbox_pending`: Verifies website applications appear in inbox; unknown universities get `status="pending"` with `matched_organization_id=None`.
5. `test_resolve_application_link_existing`: Resolves application by linking to existing org (`org-1`), creates contact and interaction, transitions inbox to `processed`.
6. `test_resolve_application_create_new`: Resolves application with `create_new`, creates new `Organization`, `OrganizationContact`, and `Interaction`.
7. `test_resolve_application_reject`: Resolves application with `reject` and reason, transitions inbox to `rejected`.
8. `test_resolve_application_idempotency`: Replaying resolve with identical key returns cached result; different payload returns `409 IDEMPOTENCY_CONFLICT`.
9. `test_learning_metrics_showcase`: `GET /api/v1/integrations/metrics` aggregates totals (students, cohorts) with program filtering.
10. `test_rbac_and_152_fz_isolation`: Manager calling `/api/v1/integrations/*` receives `403 FORBIDDEN`; Manager B attempting to view a reconciled card assigned to Manager A receives `404 NOT_FOUND`.

---

## 5. Verification Method

To independently verify the architecture and implementation:

1. **Unit and Integration Test Run**:
   ```bash
   backend/.venv/bin/pytest backend/tests/ -v
   ```
   **Pass condition**: All existing 48 tests pass + new tests in `test_integrations.py` pass $\implies$ total $> 55$ passed tests (0 failures, 0 errors).

2. **Verification Scripts**:
   ```bash
   python3 docs/checks/verify_workflow.py
   python3 docs/checks/verify_reports.py
   python3 docs/checks/verify_plan.py
   ```
   **Pass condition**: All three return exit code `0` and print `PASS`.

3. **Ponytail Audit**:
   - Verify `git status` shows 0 changes to `requirements.txt` or `package.json`.
   - Verify that all date/hash operations use standard library (`hashlib`, `uuid`, `datetime`).

4. **Invalidation Conditions**:
   - Any failure in existing 48 tests.
   - Manager role being able to perform integration sync (must be strictly 403).
   - Duplicate records created when syncing identical envelopes twice (must be 0 duplicates created).
