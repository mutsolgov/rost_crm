## 2026-09-19T18:51:18Z

You are the Specification Miner for the rost_crm project (Survey phase for Enterprise Core & Analytics Engine).

Your working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/spec_miner_survey_2
Project workspace root: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Original user request file: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md

Your mission:
Extract and map the authoritative specifications, data models, contracts, and edge cases for the package:
1. R1: Secure file storage in backend/app/files.py and endpoints in backend/app/main.py:
   - Exactly 10 formats: png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx.
   - Magic bytes / MIME signature mapping for all 10 formats.
   - Size limit: 25MB (413 status).
   - Forbidden extensions/executables (exe, sh, bat, php, etc. -> 422).
   - Storage directory path, SHA-256 calculation, UUID storage name, 152-FZ scope check on download.
2. R2: Analytics engine and binary export in backend/app/services.py & reports_export.py:
   - Read docs/planning/05-report-fixture.json to see exact structure, fields, and calculations for snapshot, activity (specifically owner_at_event historical resolution), and created reports.
   - Read requirements for XLSX binary export (OpenXML/zipfile with PK\x03\x04 signature, Rostelecom purple header #7700FF, alternating rows #F4F5F8, borders, metadata sheet).
   - Read requirements for multi-page vector PDF export (%PDF- signature, Rostelecom letterhead, page numbering "Стр. X из Y", confidentiality notice).
   - JSON export structure.
3. R3: Two-phase import wizard in backend/app/importer.py:
   - Preview dry-run endpoint (/api/v1/imports/organizations/preview) output schema: rows_total, valid_count, error_count, preview_rows, errors.
   - Commit transactional endpoint (/api/v1/imports/organizations/commit) with Idempotency-Key.
   - Supported tabular formats (XLSX, XLS, CSV) and column mappings.
4. R4: Interactive workflow graph (docs/planning/04-base-workflow.json: 13 working + 2 terminal states) and report funnel diagrams.
