## 2026-09-19T22:25:00Z
You are the Backend Lead Architect for the rost_crm project (Iteration 2: Remediation of Catalog Import Wizard).

Your working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3
Project workspace root: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Original user request file: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md

Read the following reference documents first:
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/auditor_victory_2/handoff.md (CRITICAL: Contains exact reproduction of Victory Auditor failure and patch requirements)
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_2/PROJECT.md
- AGENTS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You EXCLUSIVELY OWN:
- backend/app/main.py
- backend/app/importer.py
- backend/tests/test_import_wizard.py

Your mission:
1. Fix `backend/app/main.py:import_organizations_commit`:
   - Inspect Content-Type of request:
     - If `multipart/form-data`: Use `_extract_uploaded_file` to extract the file, call `parse_tabular_file(file_bytes, filename)` to get the rows, and pass them to `commit_organizations_import(db, user, rows, idempotency_key)`.
     - Else (JSON): Parse `body = await request.json()`, extract `rows = body.get("rows", []) if isinstance(body, dict) else body`, and pass to `commit_organizations_import(db, user, rows, idempotency_key)`.
   - This ensures BOTH multipart/form-data uploads and JSON row payloads are seamlessly supported by the commit endpoint!
2. Fix `backend/app/importer.py:preview_organizations_import`:
   - In each entry of `preview_rows`, populate BOTH flat fields and nested `data`:
     - `row_number`: idx (and `row_index`: idx)
     - `organization_name`: name
     - `org_type`: org_type
     - `contact_name`: row.get("contact_name")
     - `contact_position`: row.get("position")
     - `contact_email`: row.get("email")
     - `contact_phone`: row.get("phone")
     - `program_name`: row.get("program")
     - `product_name`: row.get("product")
     - `is_valid`: len(row_errors) == 0
     - `errors`: row_errors
     - `data`: {"name": name, "type": org_type, "contact_name": ..., "program": ..., "product": ..., "contract_number": ...}
3. Update `backend/tests/test_import_wizard.py`:
   - Add a test for `POST /api/v1/imports/organizations/commit` using multipart/form-data file upload (the exact case that failed in Victory Audit).
   - Ensure preview test verifies both flat attributes and nested `data`.
4. Run tests:
   PYTHONPATH=. /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/bin/pytest backend/tests/
   Ensure all tests pass.

Deliver your handoff report in:
/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3/handoff.md
Send a message to parent when complete with summary and path to your handoff.
