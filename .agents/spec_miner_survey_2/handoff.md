# Handoff Report: Specification Mining Survey (Enterprise Core & Analytics Engine)

**Agent Archetype**: Specification Miner  
**Workspace Root**: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm`  
**Report Location**: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_survey_2/handoff.md`  
**Date / Timestamp**: `2026-09-19T18:55:00Z`  
**Target Package**: Enterprise Core & Analytics Engine (Tasks B18.2, B22, B24, B25, B12/B13, B16; AC02, AC03, AC10, AC11, AC13, AC14, AC16, AC17)

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | R1: Storage | 10 Formats Whitelist & Validation | Support exactly 10 formats (png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx) via magic bytes & MIME header analysis in `backend/app/files.py`. | Uploaded file binary stream, file extension | File validation metadata (format code, MIME type, verified boolean) | 422 `FILE_TYPE_NOT_ALLOWED` if extension or magic bytes not in whitelist or mismatch | `ORIGINAL_REQUEST.md:136-137`, `03-acceptance-scenarios.md:133` (AC10) |
| 2 | R1: Storage | 25MB File Size Enforcement | Strict file upload limit of 25MB ($26,214,400$ bytes) checked before or during streaming. | File payload bytes | Validated size | 413 `FILE_TOO_LARGE` if payload > 25MB | `ORIGINAL_REQUEST.md:138`, `AGENTS.md:Section 3.3` |
| 3 | R1: Storage | Filename Sanitization & Path Traversal Defense | Stripping path traversal vectors (`../`, `..\\`, `/`, `\`, null bytes, control chars); storing file on disk under UUID filename in isolated storage. | Raw filename string | Sanitized original filename for DB, isolated UUID path on disk | Strips dangerous characters; raises 422 if filename empty | `ORIGINAL_REQUEST.md:139`, `02-development-plan.md:54` (B18) |
| 4 | R1: Storage | SHA-256 Checksum Calculation | Stream calculation of SHA-256 hash across whole file bytes to record in `Attachment.checksum` (64 hex characters). | File byte stream | 64-char lowercase hexadecimal SHA-256 string | I/O error handling | `ORIGINAL_REQUEST.md:140`, `03-acceptance-scenarios.md:139` |
| 5 | R1: Storage | Attachment Upload Controller | `POST /api/v1/interactions/{id}/attachments` (`multipart/form-data`); verifies user scope; saves file to `storage/attachments/{interaction_id}/`; creates `Attachment` record; logs `InteractionEvent(type="attachment_uploaded")`. | `interaction_id`, `file` (UploadFile), auth headers | JSON of `Attachment` metadata (`id, file_name, file_size, content_type, checksum, created_at`) | 404 `NOT_FOUND` if interaction not in user scope; 413 if > 25MB; 422 if bad type | `ORIGINAL_REQUEST.md:142`, `backend/app/models.py:125` |
| 6 | R1: Storage | Attachment Listing Controller | `GET /api/v1/interactions/{id}/attachments`; returns metadata array for all files attached to interaction. | `interaction_id`, auth headers | JSON list of attachments metadata | 404 `NOT_FOUND` if interaction not in user scope | `ORIGINAL_REQUEST.md:143`, `01-technical-specification.md:284` |
| 7 | R1: Storage | Authorized File Download & 152-ФЗ Check | `GET /api/v1/interactions/{id}/attachments/{attachment_id}/download`; checks user `scope_clause(user)` and interaction ownership; streams file via `FileResponse` with `Content-Disposition`. | `interaction_id`, `attachment_id`, auth headers | Binary streaming response with `Content-Disposition: attachment; filename="..."; Content-Type` | 404 `NOT_FOUND` if interaction out of scope or attachment nonexistent (never disclose existence) | `ORIGINAL_REQUEST.md:144`, `AGENTS.md:Section 3.1` (152-FZ) |
| 8 | R2: Analytics | Historical Snapshot Report | `POST /api/v1/reports/snapshot`; computes state and historical owner on date `as_of` with `knowledge_cutoff` and `as_of_inclusive` flag; scopes to `scope_now(user)`. | `as_of`, `knowledge_cutoff`, `as_of_inclusive`, optional filters (`organization_ids`, `owner_ids`, etc.) | Snapshot JSON with `rows`, `total_interactions`, `counts_by_state` (all stages present), `counts_by_historical_owner` | 403 `FORBIDDEN` if missing `reports.read`; 422 if invalid dates; 422 if >5000 records | `05-report-fixture.json:18`, `03-acceptance-scenarios.md:141` (AC11), `services.py:440` |
| 9 | R2: Analytics | Historical Activity Report | `POST /api/v1/reports/activity`; computes transitions within half-open interval `[from, to)` with `received_at <= knowledge_cutoff`; resolves historical owner at event time via `owner_at_event`. | `from`, `to`, `knowledge_cutoff`, optional `historical_owner_id`, filters | Activity JSON with `event_ids`, `interaction_ids`, `total_transitions`, `counts_by_to_state`, `counts_by_historical_owner` | 403 if unauthorized; 422 if dates invalid or missing timezone | `05-report-fixture.json:19, 105-144`, `03-acceptance-scenarios.md:165` (AC13, AC14) |
| 10 | R2: Analytics | Created Interactions Report | `POST /api/v1/reports/created`; computes interactions created within interval `[from, to)` known by `knowledge_cutoff`. | `from`, `to`, `knowledge_cutoff`, filters | Created JSON with `rows`, `total_created`, `counts_by_organization`, `counts_by_owner` | 403 if unauthorized; 422 if dates invalid | `ORIGINAL_REQUEST.md:150, 159`, `01-technical-specification.md:180` |
| 11 | R2: Analytics | Binary XLSX Export Generator | Standalone generator in `reports_export.py` using Python stdlib `zipfile` and OpenXML XML templates; magic bytes `PK\x03\x04`; styled with Rostelecom purple header (`#7700FF`), alternating zebra rows (`#F4F5F8`), thin borders (`#E2E5EB`), auto-fit column widths, metadata worksheet. | Report dataset (Snapshot, Activity, or Created) | Binary `.xlsx` file (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`) | 422 on bad parameters; handles empty data gracefully | `ORIGINAL_REQUEST.md:151-153`, `03-acceptance-scenarios.md:201` (AC16) |
| 12 | R2: Analytics | Multi-Page Vector PDF Export Generator | Standalone generator in `reports_export.py` generating pure vector PDF (`%PDF-`); includes ПАО «Ростелеком» brand letterhead, metadata block, paginated table with repeated column headers, confidentiality label, footer page numbering ("Стр. X из Y"). | Report dataset | Binary `.pdf` stream (`application/pdf`) | 422 on bad parameters | `ORIGINAL_REQUEST.md:154-155`, `03-acceptance-scenarios.md:201` (AC16) |
| 13 | R2: Analytics | JSON File Export | JSON export endpoint returning structured JSON file with `Content-Disposition: attachment; filename="rtk-report-{type}.json"` and `X-Report-Format: json`. | Report dataset | JSON attachment download | Standard API error format | `ORIGINAL_REQUEST.md:157, 160`, `01-technical-specification.md:210` |
| 14 | R3: Importer | Tabular File Parser (CSV/XLSX/XLS) | Parser in `backend/app/importer.py` reading CSV (comma/semicolon/tab; UTF-8, CP1251) and XLSX (via stdlib `zipfile` + `xml.etree.ElementTree`); maps Russian and English header synonyms. | Uploaded tabular file byte stream | Normalized table rows: list of dicts with recognized fields | 422 `FILE_TYPE_NOT_ALLOWED` if unsupported format | `ORIGINAL_REQUEST.md:162-163`, `03-acceptance-scenarios.md:33` (AC02) |
| 15 | R3: Importer | Preview Dry-Run Endpoint | `POST /api/v1/imports/organizations/preview`; parses file without DB mutation; validates rows; checks organization duplicates and program/product compatibility; outputs validation summary. | `file` (UploadFile), auth headers | JSON: `{import_id, rows_total, valid_count, error_count, preview_rows, errors}` | 403 if missing `organizations.create`; 422 if unparseable | `ORIGINAL_REQUEST.md:164`, `03-acceptance-scenarios.md:45` (AC03) |
| 16 | R3: Importer | Transactional Commit with Idempotency-Key | `POST /api/v1/imports/organizations/commit`; atomic DB transaction; creates Organizations, Contacts, Contracts, Licenses; deduplicates via `Idempotency-Key` (up to 200 chars). | `Idempotency-Key` header, payload/import_id | JSON: `{status: "committed", created_organizations, updated_organizations, created_contacts, ...}` | 409 `IDEMPOTENCY_CONFLICT` on payload mismatch; atomic rollback on DB error | `ORIGINAL_REQUEST.md:165`, `01-technical-specification.md:218` |
| 17 | R4: Workflow | Authoritative 15-State Workflow Graph | Full declarative state machine from `04-base-workflow.json`: 13 working states + 2 terminal states (`completed`, `cancelled`); 29 transitions (13 linear, 1 skip optional, 1 rework loop, 1 cycle loop, 13 cancellations). | Current state code, transition command | Allowed transitions list with `comment_required` and `condition_refs` | 409 `TRANSITION_NOT_ALLOWED` if transition invalid; 422 if required comment missing | `04-base-workflow.json:31-285`, `backend/app/workflow.py:1-19` |
| 18 | R4: Workflow | Condition Guard: `program_and_product_identified` | Enforces that transition from `document_signing` to `materials_transfer` (and all subsequent working states) requires `program_id` and `product_id` to be non-null. | Interaction attributes | Boolean condition status | 422 `VALIDATION_ERROR` if transition attempted without program or product | `04-base-workflow.json:18-30, 168`, `backend/app/workflow.py:9-12` |
| 19 | R4: UI & Funnel | Report Funnel & Distribution Visuals | Interactive SVG/Canvas diagram in `Reports.tsx` and `WorkflowGraphView.tsx` rendering active counts per stage and drop-off conversion rates using Rostelecom Gen2 palette (`#7700FF`, `#FF4F12`, `#F4F5F8`, `#101828`). | Snapshot / Activity aggregation data | SVG / Canvas interactive visual nodes | Graceful empty-state if no data | `ORIGINAL_REQUEST.md:174, 178`, `docs/planning/adr/001-ui-design-system-and-full-scope.md` |

---

## Edge Cases

| # | Feature | Input | Observed / Expected Behavior |
|---|---------|-------|------------------------------|
| 1 | R1: Storage | Executable disguised as PDF (e.g. `malware.exe` renamed to `contract.pdf`) | File extension passes `.pdf` check, but magic bytes do NOT begin with `%PDF-` (`25 50 44 46 2D`). File rejected with HTTP 422 `FILE_TYPE_NOT_ALLOWED`. |
| 2 | R1: Storage | File size exceeding 25MB by 1 byte ($26,214,401$ bytes) | Streaming or Content-Length check detects size > 25MB. File rejected immediately with HTTP 413 `FILE_TOO_LARGE`. Disk storage is not polluted. |
| 3 | R1: Storage | Filename containing path traversal (`../../etc/passwd` or `..\\windows\\win.ini`) | Path sanitization strips all directory separators and parent path segments using `pathlib.PurePath(name).name`. Saved disk filename uses UUID. DB stores cleaned basename. |
| 4 | R1: Storage | Cross-manager attachment access (Manager B attempts to download attachment of Manager A's card) | Scope check `scoped_interaction(db, user, interaction_id)` fails. Server returns strictly HTTP 404 `NOT_FOUND` (no metadata or existence of interaction is revealed). |
| 5 | R1: Storage | Attachment requested for interaction where user has access, but attachment ID belongs to a different interaction | Query requires `Attachment.id == attachment_id` AND `Attachment.interaction_id == interaction_id`. Returns HTTP 404 `NOT_FOUND`. |
| 6 | R2: Analytics | Snapshot query with `as_of` where an interaction has events after `as_of` | Events after `as_of` are ignored. Snapshot replays only events with `effective_at <= as_of` (if `as_of_inclusive=true`) and `received_at <= knowledge_cutoff`. State matches historical point. |
| 7 | R2: Analytics | Snapshot query with `as_of` before interaction creation | Interaction has no known `initial_state` or `created` event before `as_of`. Interaction is omitted from `rows` and `interaction_ids`. (Verified by FX-S01-FX-S07 in `05-report-fixture.json`). |
| 8 | R2: Analytics | Activity report with transition exactly on interval boundary `to` (`effective_at == to`) | Interval is half-open `[from, to)`. Event exactly on `to` is excluded. (Verified by FX-A01: event `I1-T3` at `2026-09-10T00:00:00Z` excluded when `to="2026-09-10T00:00:00Z"`). |
| 9 | R2: Analytics | Historical owner resolution in Activity when card was reassigned multiple times | `owner_at_event` chooses the assignment event with max `(effective_at, sequence)` that occurred at or before the transition event `(transition.effective_at, transition.sequence)` and received before cutoff. Transition owner reflects who owned it at the transition instant, even if current owner is different. |
| 10 | R2: Analytics | Zero buckets in `counts_by_state` and `counts_by_to_state` | Stages with 0 interactions or 0 transitions MUST be present in the output dictionary with value `0`, whereas owner counts only include non-empty entries. (Authoritative requirement in `05-report-fixture.json:23`). |
| 11 | R2: Analytics | XLSX export containing formula-like text (e.g. `=1+1` in interaction title) | Cell type explicitly set to inline string (`t="inlineStr"` or `t="s"`) so Excel does not execute malicious formulas (CSV/Excel Formula Injection protection). |
| 12 | R2: Analytics | PDF export with large dataset (e.g. 50+ rows across multiple pages) | Table auto-paginates across pages. Each page repeats table header row. Footer renders "Стр. X из Y" with correct total page count Y. |
| 13 | R3: Importer | Duplicate organization name in file rows | Preview flags duplicate rows within the same import payload. User is warned of duplicate row index. |
| 14 | R3: Importer | Organization name already exists in database | Preview detects existing organization by name. Action is set to `update` or `link`, rather than failing or creating a duplicate DB record. |
| 15 | R3: Importer | Re-submitting commit with identical `Idempotency-Key` | `begin_command` matches key and user; returns stored `CommandResult.response` without re-inserting organizations or contacts. |
| 16 | R3: Importer | Submitting commit with same `Idempotency-Key` but modified payload | Hash mismatch detected (`saved.payload_hash != digest`). Returns HTTP 409 `IDEMPOTENCY_CONFLICT`. |
| 17 | R4: Workflow | Backward transition (e.g. `document_signing` -> `document_revision` or cancellation) with empty comment | Transition fails with HTTP 422 `VALIDATION_ERROR` ("Для возврата, цикла или отмены нужен комментарий"). |
| 18 | R4: Workflow | Forward transition to `materials_transfer` without `program_id` and `product_id` | Enforces `program_and_product_identified`. Transition rejected with HTTP 422 `VALIDATION_ERROR`. |
| 19 | R4: Workflow | Transition from terminal state (`completed` or `cancelled`) | Terminal states have empty `allowed_transitions`. Any transition attempt returns HTTP 409 `TRANSITION_NOT_ALLOWED`. |

---

## 5-Component Handoff Report

### 1. Observation
1. **Existing Base Code**:
   - `backend/app/models.py`: lines 70–136 already contain `OrganizationContact`, `Contract`, `License`, `Interaction`, and `Attachment` models with exact column definitions (`file_name`, `file_path`, `file_size`, `content_type`, `checksum`, `uploaded_by`, `visit_id`).
   - `backend/app/main.py`: Currently implements basic interaction lifecycle, catalogs, and a single JSON snapshot endpoint (`/api/v1/reports/snapshot`). It lacks attachments controllers, multi-format export, activity/created reports, and the import wizard.
   - `backend/app/workflow.py`: Loads `backend/app/data/base-workflow.json` which is identical to `docs/planning/04-base-workflow.json`.
   - `backend/app/services.py`: Implements `begin_command`, `finish_command`, `cas`, `scoped_interaction`, and `snapshot` (lines 440–473).
2. **Authoritative Fixtures and Verification Oracles**:
   - `docs/planning/05-report-fixture.json` and `docs/checks/verify_reports.py`: Define exact mathematical oracle for `compute_snapshot`, `compute_activity`, and `owner_at_event`. Ran `python3 docs/checks/verify_reports.py` -> 12 exact report test cases (`FX-S01` to `FX-S07`, `FX-A01` to `FX-A05`) PASS.
   - `docs/planning/04-base-workflow.json` and `docs/checks/verify_workflow.py`: Ran verification script -> PASS: 13 working states, 2 terminal states, 29 transitions, initial state `contact_search`.
   - `docs/planning/02-development-plan.md` and `docs/checks/verify_plan.py`: Ran plan check -> PASS: 40 tasks, Gates D, P-ready, P-done, O verified.
   - `backend/tests/test_working_slice.py` & `test_interaction_patch.py`: Ran with `.venv/bin/pytest tests` -> 27 passed in 9.11s.
3. **Dependencies & Runtime Environment**:
   - Python virtualenv at `backend/.venv` (Python 3.14.7, FastAPI 0.141.1, SQLAlchemy 2.0.54, Pydantic 2.13.5).
   - No external libraries for Excel (`openpyxl`), PDF (`reportlab`), or file magic (`python-magic`).
   - All file analysis, XLSX generation/parsing, and PDF generation must be executed strictly with Python standard library (`zipfile`, `hashlib`, `xml.etree.ElementTree`, `csv`, `io`, `pathlib`) in alignment with the Ponytail Ladder philosophy and project rules (`AGENTS.md:Section 1 & 5`).

### 2. Logic Chain
1. **R1 (Secure File Storage)**:
   - *Premise*: Acceptance scenario AC10 and ТЗ require supporting 10 file formats (`png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx`) up to 25MB while rejecting dangerous executables (`exe, sh, php, etc.`).
   - *Inference*: Relying only on file extensions is unsafe because users can rename `.exe` to `.pdf`. Therefore, `backend/app/files.py` must inspect leading header bytes (magic bytes):
     - PNG: `89 50 4E 47 0D 0A 1A 0A`
     - JPEG: `FF D8 FF`
     - PDF: `25 50 44 46 2D` (`%PDF-`)
     - ZIP: `50 4B 03 04`, `50 4B 05 06`, `50 4B 07 08`
     - GZIP: `1F 8B`
     - RAR: `52 61 72 21 1A 07`
     - DOC & XLS: `D0 CF 11 E0 A1 B1 1A E1` (CFBF / OLE2)
     - DOCX & XLSX: `50 4B 03 04` with OpenXML component validation
   - *Inference*: 152-ФЗ compliance mandates that `GET /api/v1/interactions/{id}/attachments/{attachment_id}/download` must enforce `scoped_interaction(db, user, interaction_id)`. If an unauthorized manager tries to download another manager's attachment, return `404 Not Found` (never disclose existence).
2. **R2 (Analytics Engine & Multi-Format Export)**:
   - *Premise*: The report calculation logic must match `05-report-fixture.json` and `verify_reports.py`.
   - *Inference*: In Activity reports, transitions must be evaluated over the half-open interval `[from, to)` with `received_at <= knowledge_cutoff`. The historical owner must be derived from `InteractionEvent` assignments (`owner_changed`) strictly where `(effective_at, sequence) <= (transition.effective_at, transition.sequence)` and `received_at <= cutoff`.
   - *Inference*: Per Ponytail rules and `ORIGINAL_REQUEST.md`, XLSX files must be valid OpenXML packages starting with `PK\x03\x04` generated using standard library `zipfile` and XML templates. Styling must feature Rostelecom purple header `#7700FF` with white text, alternating rows `#F4F5F8`, thin borders `#E2E5EB`, and auto-fitted column widths.
   - *Inference*: Multi-page vector PDF files must start with `%PDF-` and be generated without heavy binary dependencies by writing standard PDF 1.4 objects (`Catalog`, `Pages`, `Page`, `Font`, `Contents`), featuring Rostelecom letterhead, repeated headers on every page, confidentiality mark, and page numbers formatted as "Стр. X из Y".
3. **R3 (Two-Phase Import Wizard)**:
   - *Premise*: AC02 and AC03 mandate a dry-run preview before commit, preventing accidental duplicates and database pollution.
   - *Inference*: Phase 1 (`POST /api/v1/imports/organizations/preview`) parses XLSX (via `zipfile` + XML) or CSV (via `csv`), maps column headers fuzzily, validates data, detects existing records, and returns preview statistics (`rows_total`, `valid_count`, `error_count`, `preview_rows`, `errors`) without executing any DB commit.
   - *Inference*: Phase 2 (`POST /api/v1/imports/organizations/commit`) wraps the insertions into an atomic transaction and requires `Idempotency-Key` (using `begin_command` / `finish_command`), guaranteeing idempotent retries.
4. **R4 (Workflow Graph & Funnel Diagrams)**:
   - *Premise*: `04-base-workflow.json` is the sole source of truth for the process lifecycle (13 working + 2 terminal states, 29 transitions).
   - *Inference*: The frontend components (`WorkflowGraphView.tsx` and `Reports.tsx`) must display all 15 states, visual funnel bars for stage occupancy, and conversion drop-offs using the Rostelecom Gen2 palette (`#7700FF`, `#FF4F12`, `#F4F5F8`, `#101828`).

### 3. Caveats
1. **Legacy BIFF vs OpenXML**: Legacy binary `.xls` files (Excel 97–2003 BIFF8) and `.doc` share the OLE2 Compound Document container signature (`\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1`). Parsing legacy BIFF records without external C libraries requires binary record unpacking; however, modern exports and standard CRM imports predominantly use `.xlsx` or `.csv`. The importer handles modern `.xlsx` via stdlib `zipfile` and `.csv` via stdlib `csv` cleanly; for `.xls`, support structured tabular data or CFBF envelope detection.
2. **Synchronous Report Boundary**: Per `services.py:446`, synchronous report queries are limited to 5000 records (`REPORT_LIMIT_EXCEEDED` if exceeded). Very large datasets should leverage asynchronous jobs in future tasks (B23).
3. **Font Encoding in Pure Vector PDF**: In a standard-library-only pure vector PDF writer, Cyrillic text rendering requires either embedding standard WinAnsi / CP1251 font encoding dictionary or minimal TrueType subsetting. Ensuring Cyrillic glyph display with standard PDF Type1 / TrueType font structures must be verified in test assertions.

### 4. Conclusion
1. All data contracts, endpoints, schemas, magic signatures, validation rules, and acceptance criteria for R1, R2, R3, and R4 have been rigorously extracted, verified against authoritative sources (`ORIGINAL_REQUEST.md`, `01-technical-specification.md`, `04-base-workflow.json`, `05-report-fixture.json`, `verify_reports.py`), and mapped into detailed feature and edge-case tables.
2. The implementation strategy respects the **Ponytail Ladder**:
   - `files.py`: Standard library `hashlib`, `pathlib`, `io`, `uuid`.
   - `reports_export.py`: Standard library `zipfile`, `xml.etree.ElementTree`, `io.BytesIO`.
   - `importer.py`: Standard library `csv`, `zipfile`, `xml.etree.ElementTree`.
   - Zero new dependencies in `requirements.txt` or `package.json`.
3. 100% test integrity of the baseline is confirmed (27 pytest tests pass, 3 doc verification oracles pass).

### 5. Verification Method
To independently verify the facts, contracts, and baseline integrity:
1. **Doc Verification Scripts**:
   ```bash
   python3 docs/checks/verify_workflow.py
   python3 docs/checks/verify_reports.py
   python3 docs/checks/verify_plan.py
   ```
   *Expected*: All 3 return exit code 0 and output `PASS` (verifying 15 workflow states, 12 report fixture test cases, 40 plan tasks).
2. **Current Backend Test Suite**:
   ```bash
   cd backend && PYTHONPATH=. .venv/bin/pytest tests
   ```
   *Expected*: All 27 tests pass in ~9 seconds with 0 failures.
3. **Authoritative Specification Inspection**:
   - Review `04-base-workflow.json` lines 31–285 for the exact 15 states and 29 transitions.
   - Review `05-report-fixture.json` lines 14–34 for exact semantics of `snapshot`, `activity`, `owner_at_event`, and `knowledge_cutoff`.
   - Review `ORIGINAL_REQUEST.md` lines 108–221 for exact requirements of Enterprise Core & Analytics Engine.
