# Project: rost_crm — Enterprise Core & Analytics Engine

## Architecture
- Backend: FastAPI, SQLAlchemy 2.0, SQLite (in tests) / PostgreSQL (in prod), stdlib `zipfile` + XML for XLSX, pure vector PDF 1.4 for PDF, stdlib `email` / multipart handling, standard `csv`. Zero new pip dependencies per Ponytail Ladder.
- Security Invariants: 152-FZ scope isolation (`scope_clause`, 404 on out-of-scope), in-memory JWT, CAS revision check, Idempotency-Key (`begin_command` / `finish_command`).
- Frontend: React 19, TypeScript, Rostelecom Gen2 Light Theme CSS tokens (`#7700FF`, `#FF4F12`, `#F4F5F8`, `#101828`), native SVG/Canvas diagrams, zero external charting or upload libraries.

## Code Layout & File Ownership
| File Path | Component | Owner |
|---|---|---|
| `backend/app/files.py` | Secure storage, magic bytes (10 formats), 25MB limit, SHA-256 | Backend Lead Architect |
| `backend/app/reports_export.py` | Multi-format export (OpenXML XLSX, vector PDF, JSON) | Backend Lead Architect |
| `backend/app/importer.py` | Tabular parser (CSV, XLSX), dry-run preview, atomic commit | Backend Lead Architect |
| `backend/app/schemas.py` | Pydantic schemas for reports, attachments, imports | Backend Lead Architect |
| `backend/app/services.py` | Business logic for reports (snapshot, activity, created) | Backend Lead Architect |
| `backend/app/main.py` | API endpoints (/attachments, /reports, /imports) | Backend Lead Architect |
| `backend/app/config.py` | Storage directory settings | Backend Lead Architect |
| `frontend/src/api.ts` | API client (`upload`, `downloadGet`) | Frontend & UX Lead |
| `frontend/src/types.ts` | Frontend interfaces (Attachment, Reports, Import) | Frontend & UX Lead |
| `frontend/src/styles.css` | UI styles & format badges in Gen2 palette | Frontend & UX Lead |
| `frontend/src/App.tsx` | Route integration & prop forwarding | Frontend & UX Lead |
| `frontend/src/views/InteractionPage.tsx` | Attachments section & drag-and-drop uploader | Frontend & UX Lead |
| `frontend/src/views/Reports.tsx` | 3 report modes, export buttons, SVG funnel diagram | Frontend & UX Lead |
| `frontend/src/views/ReferenceViews.tsx` | 3-step import wizard modal | Frontend & UX Lead |
| `frontend/src/views/WorkflowGraphView.tsx` | 15-state workflow graph (13 working + 2 terminal) | Frontend & UX Lead |
| `backend/tests/test_attachments.py` | QA test suite for R1 | QA & Forensic Test Engineer |
| `backend/tests/test_reports_multiformat.py` | QA test suite for R2 | QA & Forensic Test Engineer |
| `backend/tests/test_import_wizard.py` | QA test suite for R3 | QA & Forensic Test Engineer |
| `backend/tests/conftest.py` | Test fixtures & isolated storage path | QA & Forensic Test Engineer |

## Feature Inventory
| # | Feature | Description | Milestone | Status |
|---|---|---|---|---|
| F01 | Secure File Storage Engine | 10 formats magic bytes/MIME, 25MB limit (413), path traversal defense, UUID disk filename, SHA-256 in `backend/app/files.py` | M1 | DONE |
| F02 | Attachments API Endpoints | `POST /api/v1/interactions/{id}/attachments`, `GET .../attachments`, `GET .../download` with streaming FileResponse and 152-FZ scope (404) | M1 | DONE |
| F03 | Attachment Serialization in Detail | Include attachments list in `services.py:detail()` and `interaction_dict()` | M1 | DONE |
| F04 | Analytics Engine 3 Modes | `snapshot` (cutoff, as_of), `activity` (`owner_at_event` per 05-report-fixture), `created` in `services.py` | M1 | DONE |
| F05 | Binary Multi-Format Exporter | OpenXML XLSX (`PK\x03\x04`, #7700FF, alternating rows, metadata sheet), multi-page vector PDF (`%PDF-`, letterhead, page numbering), JSON in `reports_export.py` | M1 | DONE |
| F06 | Reports API Endpoints | `POST /api/v1/reports/snapshot/export`, `/activity` + `/export`, `/created` + `/export` in `main.py` | M1 | DONE |
| F07 | Tabular Parser (CSV/XLSX) | Pure stdlib parser for CSV and XLSX via `zipfile`+XML in `importer.py` | M1 | DONE |
| F08 | Two-Phase Import Wizard Endpoints | Dry-run preview `/api/v1/imports/organizations/preview` and transactional commit `/commit` with Idempotency-Key | M1 | DONE |
| F09 | Attachments UI & Uploader | Attachments section in `InteractionPage.tsx` with format badges, metadata, download button, 25MB drag-and-drop uploader | M2 | DONE |
| F10 | Reports UI & SVG Funnel | 3 report modes in `Reports.tsx`, download buttons (XLSX, PDF, JSON), interactive SVG/Canvas stage distribution diagram | M2 | DONE |
| F11 | 3-Step Import Wizard Modal | Modal in `ReferenceViews.tsx`: Upload -> Preview & Validation -> Commit with progress bar | M2 | DONE |
| F12 | Workflow Graph Visualization | Component in `WorkflowGraphView.tsx` rendering 13 working + 2 terminal states with active node highlight | M2 | DONE |
| F13 | Frontend API & Types | Add `upload` and `downloadGet` to `api.ts`, add Attachment, Reports, and Import interfaces to `types.ts` | M2 | DONE |
| F14 | Comprehensive QA Test Suites | `test_attachments.py`, `test_reports_multiformat.py`, `test_import_wizard.py` (47 tests total, 100% PASS) | M3 | DONE |
| F15 | Specification & Plan Checks | `verify_workflow.py`, `verify_reports.py`, `verify_plan.py` all PASS | M3 | DONE |
| F16 | Architecture & Ponytail Review | Ponytail Ladder review (stdlib-first, zero bloat, security invariants): APPROVE | M4 | DONE |
| F17 | Forensic Integrity Audit | Forensic verification (no dummy mocks, authentic logic, binary veto): CLEAN | M4 | DONE |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M0 | Survey & Specification Mapping | Codebase and specification discovery | none | DONE |
| M1 | Backend Lead Architect | R1 (Files), R2 (Reports/Analytics), R3 (Importer) | M0 | DONE |
| M2 | Frontend & UX Lead | R4 (Attachments, Reports, Import Wizard, Workflow Graph) | M0 | DONE |
| M3 | QA & Forensic Test Engineer | R5 (Test suites test_attachments, test_reports_multiformat, test_import_wizard, verify_*.py) | M1 | DONE |
| M4 | Architecture Reviewer & Ponytail Guardian | Ponytail review (APPROVE) + Forensic Audit (CLEAN) | M1, M2, M3 | DONE |
