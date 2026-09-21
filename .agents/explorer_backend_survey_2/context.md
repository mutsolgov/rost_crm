# Context for Backend Explorer (Survey Phase)

- Working Directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_survey_2
- Mission: Investigate existing backend architecture, files, endpoints, database models, and test runner.
- Key inspection targets:
  - backend/app/main.py, models.py, schemas.py, services.py, auth.py, database.py, seed.py
  - Check if backend/app/files.py, reports_export.py, importer.py exist or if any stubs exist
  - backend/tests/test_working_slice.py, backend/tests/test_interaction_patch.py
  - Check how pytest is invoked (virtualenv path, etc.)
  - Check database migration/tables creation logic in backend/app/database.py
- Output: handoff.md in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_backend_survey_2/handoff.md
