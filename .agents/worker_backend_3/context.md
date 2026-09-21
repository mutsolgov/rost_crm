# Context for Backend Lead Architect (Iteration 2 Remediation)

- Working Directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3
- Objective: Remediate the Catalog Import Wizard contract mismatches identified by the Victory Auditor.
- Reference:
  - /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/auditor_victory_2/handoff.md
  - /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md
  - backend/app/main.py
  - backend/app/importer.py
  - backend/tests/test_import_wizard.py
- Remediation Requirements:
  1. In `backend/app/main.py`: Update `import_organizations_commit` to support BOTH content types:
     - If `request.headers.get("content-type", "").startswith("multipart/form-data")`:
       Extract the file using `_extract_uploaded_file`, parse rows using `parse_tabular_file(file_bytes, filename)`, and pass the parsed rows to `commit_organizations_import(db, user, rows, idempotency_key)`.
     - Else (JSON): Parse `body = await request.json()`; extract `rows = body.get("rows", [])` if dict else `body`; pass rows to `commit_organizations_import`.
     - This ensures both direct multipart file uploads AND JSON row payloads are 100% supported without 500 JSONDecodeError!
  2. In `backend/app/importer.py`: Update `preview_organizations_import` preview row dictionaries to contain:
     - `row_number: idx` (and `row_index: idx`)
     - `organization_name: name`
     - `org_type: org_type`
     - `contact_name: row.get("contact_name")`
     - `contact_position: row.get("position")`
     - `contact_email: row.get("email")`
     - `contact_phone: row.get("phone")`
     - `program_name: row.get("program")`
     - `product_name: row.get("product")`
     - `is_valid: len(row_errors) == 0`
     - `errors: row_errors`
     - `data: {...}` (retain for backwards compatibility)
  3. Ensure all tests in `backend/tests/` continue to pass (100% PASS).
- Output: handoff.md in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_backend_3/handoff.md
