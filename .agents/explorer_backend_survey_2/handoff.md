# Handoff Report: Backend Technical Baseline Survey for R1, R2, R3

## 1. Observation

### 1.1. Codebase Inventory and Target Modules
Inspection of `backend/app/` via `list_dir`:
- Existing files: `__init__.py`, `auth.py`, `config.py`, `data/base-workflow.json`, `db.py`, `errors.py`, `main.py`, `models.py`, `schemas.py`, `seed.py`, `services.py`, `workflow.py`.
- Target files for R1, R2, R3:
  - `backend/app/files.py`: **DOES NOT EXIST**. Must be created for R1.
  - `backend/app/reports_export.py`: **DOES NOT EXIST**. Must be created for R2.
  - `backend/app/importer.py`: **DOES NOT EXIST**. Must be created for R3.

### 1.2. Existing Models in `backend/app/models.py`
In `backend/app/models.py` (lines 125-137), the `Attachment` model already exists in the database schema:
```python
class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    interaction_id: Mapped[str] = mapped_column(ForeignKey("interactions.id"), index=True)
    visit_id: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```
- `Interaction` model (lines 103-123) has `id`, `title`, `organization_id`, `program_id`, `product_id`, `cycle_label`, `owner_id`, `contract_id`, `license_id`, `contact_id`, `team_id`, `state`, `workflow_version`, `revision`, `visit_id`, `created_at`, `updated_at`, `closed_at`.
- Other models already declared: `User`, `Organization`, `OrganizationAccess`, `Direction`, `Program`, `Product`, `ProgramProduct`, `OrganizationContact`, `Contract`, `License`, `InteractionEvent`, `Comment`, `CommandResult`.

### 1.3. Scope, Serialization, and Idempotency in `backend/app/services.py`
- `scope_clause(user)` (lines 41-47):
  ```python
  def scope_clause(user):
      granted = select(OrganizationAccess.organization_id).where(
          OrganizationAccess.user_id == user.id, OrganizationAccess.read_all.is_(True))
      own = Interaction.owner_id == user.id if user.role == "manager" else false()
      team = ((Interaction.team_id == user.team_id) if user.role == "supervisor" and user.team_id
              else false())
      return or_(own, team, Interaction.organization_id.in_(granted))
  ```
  And `scoped_interaction(db, user, interaction_id)` (lines 50-54) returns the interaction if visible, or raises `APIError("NOT_FOUND", "Взаимодействие не найдено.", 404)` to enforce 152-ФЗ confidentiality.
- `interaction_dict(db, item)` (lines 91-113): Serializes `id`, `title`, `organization_id`, `organization_name`, `program_id`, `program_name`, `product_id`, `product_name`, `direction_name`, `contact_id`, `contact_name`, `contract_id`, `contract_number`, `license_id`, `license_status`, `cycle_label`, `owner_id`, `owner_name`, `state`, `state_name`, `workflow_version`, `revision`, `created_at`, `updated_at`, `closed_at`.
- `detail(db, user, interaction_id)` (lines 143-152): Returns `interaction_dict`, `allowed_transitions`, `events`, and `comments`. Currently does NOT serialize `attachments`.
- Idempotency via `begin_command` and `finish_command` (lines 155-186):
  Requires non-empty `Idempotency-Key` (up to 200 characters). Computes SHA-256 hash of request body (`separators=(",", ":")`), writes or reads `CommandResult`. If key is reused with differing payload, returns `409 IDEMPOTENCY_CONFLICT`. Replayed responses verify `scoped_interaction(db, user, saved.resource_id)`.

### 1.4. Error Handling Envelope in `backend/app/errors.py`
In `backend/app/errors.py` (lines 8-27):
```python
class APIError(Exception):
    def __init__(self, code, message, status=422, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details
```
Error response format is strictly:
`{"error": {"code": str, "message": str, "request_id": str, "details": optional list/dict}}`
Standard codes: `VALIDATION_ERROR` (422), `NOT_FOUND` (404), `FORBIDDEN` (403), `UNAUTHENTICATED` (401), `IDEMPOTENCY_CONFLICT` (409), `REVISION_CONFLICT` (409), `NOT_READY` (503).
For files: `FILE_TYPE_NOT_ALLOWED` (422), `FILE_TOO_LARGE` (413).

### 1.5. Existing Test Suite Execution
- Virtual environment: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv`
- Pytest version: 9.1.1, Python: 3.14.7.
- Command executed:
  `PYTHONPATH=. /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/bin/pytest`
- Output:
  `======================= 27 passed, 2 warnings in 11.15s ========================`
  - `tests/test_interaction_patch.py`: 10 passed (37%)
  - `tests/test_working_slice.py`: 17 passed (100%)
- Conftest setup (`backend/tests/conftest.py`):
  Uses `tmp_path / 'test.db'` with SQLite, initializes schema via `Base.metadata.create_all`, runs `seed_database(session)`.
  Client uses `TestClient(app)`.
  Authentication headers in tests: `{"X-Demo-User": "manager-a"}`.
- Specification oracle checks:
  Command: `python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py`
  Result: Exit code 0 (All PASS).

### 1.6. Dependencies and Runtime Environment
In `backend/requirements.txt`:
```
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
SQLAlchemy>=2.0.36,<3
psycopg[binary]>=3.2,<4
PyJWT[crypto]>=2.9,<3
pydantic>=2.9,<3
```
- `python-multipart` is NOT installed.
- No `openpyxl`, `xlsxwriter`, `reportlab`, `pypdf`, or `pandas`.
- Verified standard library capabilities:
  - Multipart parsing: Python `email.message_from_bytes(..., policy=email.policy.default)` successfully parses multipart bodies in 5 lines of stdlib code without external packages.
  - XLSX generation and parsing: Standard library `zipfile` + `xml.etree.ElementTree` can create and parse valid Office Open XML spreadsheets.
  - PDF generation: Standard library stream generation generates compliant vector PDF 1.4 documents.

---

## 2. Logic Chain

1. **R1 (Files & Attachments - B18.2, B19):**
   - The database model `Attachment` is already defined in `models.py:125-137` with exact required fields (`id`, `interaction_id`, `visit_id`, `file_name`, `file_path`, `file_size`, `content_type`, `checksum`, `uploaded_by`, `created_at`).
   - What is missing:
     - `backend/app/files.py` to handle storage (`storage/attachments/{interaction_id}/`), magic bytes validation for 10 formats (`png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx`), 25 MB size limit (`FILE_TOO_LARGE`, 413), filename path traversal sanitation, and SHA-256 calculation.
     - Routes in `backend/app/main.py`:
       - `POST /api/v1/interactions/{id}/attachments`: Checks `scoped_interaction`, validates format and size, stores file, inserts `Attachment`, appends `InteractionEvent(type="attachment_uploaded")`.
       - `GET /api/v1/interactions/{id}/attachments`: Lists attachments for visible interaction.
       - `GET /api/v1/interactions/{id}/attachments/{attachment_id}/download`: Streams `FileResponse` with `Content-Disposition`, returns 404 if interaction or attachment is outside user scope.
     - Include attachments in `services.py:detail()` response so the interaction card UI gets attachments in a single query.

2. **R2 (Analytics Engine & Multi-Format Export - B22, B24):**
   - Currently, `backend/app/services.py:snapshot()` implements only the `snapshot` report with JSON export.
   - Per `docs/checks/verify_reports.py` and `05-report-fixture.json`, the analytics engine requires three report modes:
     - `snapshot`: status at `as_of` with `knowledge_cutoff`, `as_of_inclusive`, and optional `historical_owner_id`.
     - `activity`: transitions in `[from_date, to_date)` with `owner_at_event` historical resolution and transition counts by stage, interaction, and owner.
     - `created`: interactions created in `[from_date, to_date)`.
   - Creation of `backend/app/reports_export.py`:
     - Implements multi-format exports (`json`, `xlsx`, `pdf`) using standard library:
       - `format=json`: existing JSON envelope with `Content-Disposition` attachment.
       - `format=xlsx`: pure stdlib `zipfile` OpenXML generator with Rostelecom styling (header `#7700FF`, zebra `#F4F5F8`, thin borders, auto-width, metadata sheet). Signature `PK\x03\x04`.
       - `format=pdf`: pure stdlib vector PDF 1.4 generator with Rostelecom header, page numbering ("Стр. X из Y"), table layout, confidentiality note. Signature `%PDF-1.4`.
     - Routes in `backend/app/main.py`:
       - `POST /api/v1/reports/snapshot/export` (supports `format=json|xlsx|pdf`)
       - `POST /api/v1/reports/activity` & `POST /api/v1/reports/activity/export`
       - `POST /api/v1/reports/created` & `POST /api/v1/reports/created/export`

3. **R3 (Two-Phase Import Wizard - B12, B13):**
   - Creation of `backend/app/importer.py`:
     - Reads CSV and XLSX (via `zipfile` and `xml.etree.ElementTree`) without third-party dependencies.
     - Maps columns (Organization Name, Type, Contact Name, Position, Email, Phone, Program, Product, Contract Number).
     - Phase 1: `POST /api/v1/imports/organizations/preview` (dry-run validation, returns counts, preview rows, row-level diagnostic errors; does not touch DB).
     - Phase 2: `POST /api/v1/imports/organizations/commit` (requires `Idempotency-Key`, executes within a single database transaction, creates/updates `Organization`, `OrganizationAccess`, `OrganizationContact`, `Contract`).
   - Routes in `backend/app/main.py`:
     - `POST /api/v1/imports/organizations/preview`
     - `POST /api/v1/imports/organizations/commit`

4. **Testing and Verification (R4, R5):**
   - Must add dedicated backend test suites:
     - `backend/tests/test_attachments.py`
     - `backend/tests/test_reports_multiformat.py`
     - `backend/tests/test_import_wizard.py`
   - All 27 existing tests must continue to pass (zero regression). Total tests will exceed 40.

---

## 3. Caveats

1. **Storage directory path in testing vs production:**
   In production, files should default to `storage/attachments/`. In testing (`conftest.py`), `Settings` should use `storage_dir = tmp_path / 'storage'` to avoid leaving test artifacts on disk.
2. **Multipart handling without `python-multipart`:**
   Because `python-multipart` is not currently in `requirements.txt`, using FastAPI's `File(...)` or `UploadFile` could raise a runtime error unless `python-multipart` is added or stdlib parsing is used. Implementing a robust fallback that parses multipart requests via `email.message_from_bytes(..., policy=email.policy.default)` guarantees zero external dependencies per Ponytail Ladder.
3. **PDF Cyrillic Encoding:**
   Vector PDF output in pure Python needs proper text encoding (e.g. Type 1 / WinAnsi with CP1251 octal escapes or CIDFont / UTF-16BE hex strings) to render Russian text cleanly.

---

## 4. Conclusion

The existing backend provides a solid, clean, and test-proven foundation:
- Database schema (`models.py`) already contains `Attachment`, `OrganizationContact`, `Contract`, `License`, `InteractionEvent`, `CommandResult`.
- CAS revisioning, Idempotency (`CommandResult`), and 152-ФЗ scoping (`scope_clause`, 404 masking) are mature and fully tested.
- Implementing R1, R2, and R3 requires creating 3 new app modules (`files.py`, `reports_export.py`, `importer.py`), extending `schemas.py`, `services.py`, `main.py`, `config.py`, and adding 3 new test files (`test_attachments.py`, `test_reports_multiformat.py`, `test_import_wizard.py`).
- All implementations can adhere 100% to the Ponytail Ladder (stdlib-first, zero added pip dependencies).

---

## 5. Verification Method

To independently verify this baseline:
1. Run backend tests:
   ```bash
   cd /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend
   PYTHONPATH=. .venv/bin/pytest -v
   ```
   *Expected:* 27 passed in ~11s.
2. Run specification and planning verification scripts:
   ```bash
   cd /home/muhammad/Dev/HACKATHON/LCT/rost_crm
   python3 docs/checks/verify_workflow.py
   python3 docs/checks/verify_reports.py
   python3 docs/checks/verify_plan.py
   ```
   *Expected:* All three output `PASS` and exit with code 0.
3. Invalidation conditions:
   - Any test failure in `test_working_slice.py` or `test_interaction_patch.py`.
   - Modifying `04-base-workflow.json` or `05-report-fixture.json` without updating oracles.
